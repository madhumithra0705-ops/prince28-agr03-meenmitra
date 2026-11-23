"""Polite, resumable downloader for the MeenMitra corpus."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import random
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from protego import Protego

CONTACT = "https://github.com/madhumithra0705-ops/prince28-agr03-meenmitra"
ROBOTS_TOKEN = "examate-student-bot"
USER_AGENT = f"{ROBOTS_TOKEN}/0.1 (student project; +{CONTACT})"

RETRYABLE = {408, 425, 429, 500, 502, 503, 504}
MAX_WAIT = 120
MAX_BACKOFF = 60
MAX_BYTES = 200 * 1024 * 1024
ATTEMPT_TIMEOUT = 300


@dataclass(frozen=True)
class Source:
    url: str
    source: str
    licence: str
    title: str = ""


class DownloadError(Exception):
    """Raised when a document cannot be downloaded."""


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def slug(value: str, limit: int = 70) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return value[:limit].strip("-") or "document"


def file_stem(source: Source | str) -> str:
    url = source.url if isinstance(source, Source) else source
    parsed = urlparse(url)
    original = Path(parsed.path).stem or "document"
    safe_name = slug(original)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    return f"{safe_name}-{digest}"


def pick_ext(url: str, content_type: str = "") -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".pdf", ".html", ".htm", ".csv", ".json", ".xml", ".txt"}:
        return suffix

    content_type = content_type.split(";")[0].strip().lower()
    known = {
        "application/pdf": ".pdf",
        "text/html": ".html",
        "text/csv": ".csv",
        "application/json": ".json",
        "application/xml": ".xml",
        "text/xml": ".xml",
        "text/plain": ".txt",
    }
    return known.get(content_type, ".bin")


def backoff_delay(attempt: int, *, rng: Callable[[], float] = random.random) -> float:
    ceiling = min(MAX_BACKOFF, 2.0**attempt)
    return rng() * ceiling


def retry_after_seconds(value: str | None, *, now: datetime | None = None) -> float | None:
    if not value:
        return None

    try:
        return min(MAX_WAIT, max(0.0, float(value)))
    except ValueError:
        pass

    try:
        when = parsedate_to_datetime(value)
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        current = now or datetime.now(UTC)
        return min(MAX_WAIT, max(0.0, (when - current).total_seconds()))
    except (TypeError, ValueError, OverflowError):
        return None


def read_sources(path: Path) -> list[Source]:
    """Read CSV sources, ignoring comments, blank lines and duplicate URLs."""
    sources: list[Source] = []
    seen: set[str] = set()

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        content = "".join(
            line for line in handle if line.strip() and not line.lstrip().startswith("#")
        )

    reader = csv.DictReader(io.StringIO(content))
    required = {"url", "source", "licence", "title"}

    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError(f"CSV must contain columns: {', '.join(sorted(required))}")

    for line_number, row in enumerate(reader, start=2):
        url = (row.get("url") or "").strip()
        source = (row.get("source") or "").strip()
        licence = (row.get("licence") or "").strip()
        title = (row.get("title") or "").strip()

        if not url:
            continue

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"Invalid HTTP(S) URL on CSV line {line_number}: {url}")

        if not source:
            raise ValueError(f"Missing source on CSV line {line_number}")
        if not licence:
            raise ValueError(f"Missing licence on CSV line {line_number}")

        if url in seen:
            continue

        seen.add(url)
        sources.append(Source(url, source, licence, title))

    return sources


class Manifest:
    """Append-only JSONL download record."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records: list[dict] = []

        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(record, dict):
                        self.records.append(record)

    def done(self, url: str, root: Path) -> bool:
        for record in reversed(self.records):
            if record.get("url") != url:
                continue
            if record.get("status") != "downloaded":
                return False

            relative = record.get("path")
            if not relative:
                return False

            return (Path(root) / relative).is_file()

        return False

    def add(self, record: dict) -> None:
        self.records.append(record)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


class Robots:
    """Cache and apply robots.txt rules per website."""

    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.cache: dict[str, tuple[Protego, float]] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    async def _load(self, origin: str) -> tuple[Protego, float]:
        if origin in self.cache:
            return self.cache[origin]

        lock = self.locks.setdefault(origin, asyncio.Lock())
        async with lock:
            if origin in self.cache:
                return self.cache[origin]

            try:
                response = await self.client.get(
                    f"{origin}/robots.txt",
                    headers={"User-Agent": USER_AGENT},
                    timeout=ATTEMPT_TIMEOUT,
                )

                if response.status_code == 404:
                    parser = Protego.parse("")
                elif response.status_code >= 500:
                    parser = Protego.parse("User-agent: *\nDisallow: /")
                elif response.status_code >= 400:
                    parser = Protego.parse("")
                else:
                    parser = Protego.parse(response.text)

                delay = parser.crawl_delay(ROBOTS_TOKEN) or 0.0
                result = (parser, float(delay))

            except httpx.HTTPError:
                result = (
                    Protego.parse("User-agent: *\nDisallow: /"),
                    0.0,
                )

            self.cache[origin] = result
            return result

    async def check(self, url: str) -> tuple[bool, float]:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        parser, delay = await self._load(origin)
        return bool(parser.can_fetch(url, ROBOTS_TOKEN)), delay


class HostGate:
    """Keep requests to each host separated by a minimum delay."""

    def __init__(
        self,
        delay: float = 0.5,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.delay = delay
        self.sleep = sleep
        self.locks: dict[str, asyncio.Lock] = {}
        self.last_request: dict[str, float] = {}

    async def wait(self, host: str, crawl_delay: float = 0.0) -> None:
        lock = self.locks.setdefault(host, asyncio.Lock())
        async with lock:
            required = max(self.delay, crawl_delay)
            previous = self.last_request.get(host)

            if previous is not None:
                remaining = required - (time.monotonic() - previous)
                if remaining > 0:
                    await self.sleep(remaining)

            self.last_request[host] = time.monotonic()


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=httpx.Timeout(ATTEMPT_TIMEOUT),
    )


async def _download(
    client: httpx.AsyncClient,
    url: str,
    destination: Path,
) -> dict:
    """Stream a response into a temporary file, then atomically rename it."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    digest = hashlib.sha256()
    size = 0

    try:
        async with client.stream(
            "GET",
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=ATTEMPT_TIMEOUT,
        ) as response:
            response.raise_for_status()

            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > MAX_BYTES:
                raise DownloadError("Document exceeds the maximum allowed size")

            extension = pick_ext(url, response.headers.get("content-type", ""))

            with partial.open("wb") as handle:
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise DownloadError("Document exceeds the maximum allowed size")
                    digest.update(chunk)
                    handle.write(chunk)

        if size == 0:
            raise DownloadError("Downloaded document is empty")

        final_path = destination.with_suffix(extension)
        partial.replace(final_path)

        return {
            "path": str(final_path),
            "sha256": digest.hexdigest(),
            "bytes": size,
            "content_type": response.headers.get("content-type", ""),
        }

    finally:
        if partial.exists():
            partial.unlink()


async def fetch_one(
    client: httpx.AsyncClient,
    src: Source,
    *,
    root: Path,
    raw_dir: Path,
    robots: Robots,
    gate: HostGate,
    slots: asyncio.Semaphore,
    max_attempts: int = 4,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> dict:
    """Fetch one source, respecting robots rules, host delays and retries."""
    root = Path(root)
    manifest = Manifest(root / "data" / "manifest.jsonl")

    if manifest.done(src.url, root):
        return {"url": src.url, "status": "skipped"}

    allowed, crawl_delay = await robots.check(src.url)

    base_record = {
        "url": src.url,
        "source": src.source,
        "title": src.title,
        "licence": src.licence,
    }

    if not allowed:
        record = {
            **base_record,
            "status": "blocked",
            "timestamp": now_iso(),
        }
        manifest.add(record)
        return record

    parsed = urlparse(src.url)
    destination = root / raw_dir / slug(src.source) / f"{file_stem(src)}.bin"

    async with slots:
        for attempt in range(1, max_attempts + 1):
            await gate.wait(parsed.netloc, crawl_delay)

            try:
                result = await _download(client, src.url, destination)
                relative_path = Path(result["path"]).relative_to(root)

                record = {
                    **base_record,
                    "status": "downloaded",
                    "path": str(relative_path),
                    "sha256": result["sha256"],
                    "bytes": result["bytes"],
                    "content_type": result["content_type"],
                    "attempts": attempt,
                    "timestamp": now_iso(),
                }
                manifest.add(record)
                return record

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code

                if status not in RETRYABLE or attempt >= max_attempts:
                    record = {
                        **base_record,
                        "status": "failed",
                        "error": f"HTTP {status}",
                        "http_status": status,
                        "attempts": attempt,
                        "timestamp": now_iso(),
                    }
                    manifest.add(record)
                    return record

                delay = retry_after_seconds(exc.response.headers.get("Retry-After"))
                await sleep(delay if delay is not None else backoff_delay(attempt - 1))

            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= max_attempts:
                    record = {
                        **base_record,
                        "status": "failed",
                        "error": type(exc).__name__,
                        "attempts": attempt,
                        "timestamp": now_iso(),
                    }
                    manifest.add(record)
                    return record

                await sleep(backoff_delay(attempt - 1))

            except DownloadError as exc:
                record = {
                    **base_record,
                    "status": "failed",
                    "error": str(exc),
                    "attempts": attempt,
                    "timestamp": now_iso(),
                }
                manifest.add(record)
                return record

    return {
        **base_record,
        "status": "failed",
        "error": "Attempts exhausted",
        "attempts": max_attempts,
        "timestamp": now_iso(),
    }


async def fetch_all(
    sources: list[Source],
    *,
    root: Path = Path("."),
    max_concurrency: int = 4,
    per_host_delay: float = 0.5,
    max_attempts: int = 4,
    client: httpx.AsyncClient | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    on_result: Callable[[dict], None] | None = None,
) -> dict[str, int]:
    """Download a collection of sources and return status counts."""
    root = Path(root)
    raw_dir = Path("data/raw")
    owns_client = client is None
    active_client = client or make_client()

    robots = Robots(active_client)
    gate = HostGate(per_host_delay, sleep)
    slots = asyncio.Semaphore(max_concurrency)

    counts = {
        "downloaded": 0,
        "skipped": 0,
        "blocked": 0,
        "failed": 0,
    }

    try:

        async def run_one(src: Source) -> None:
            result = await fetch_one(
                active_client,
                src,
                root=root,
                raw_dir=raw_dir,
                robots=robots,
                gate=gate,
                slots=slots,
                max_attempts=max_attempts,
                sleep=sleep,
            )
            status = result.get("status", "failed")
            counts[status] = counts.get(status, 0) + 1

            if on_result is not None:
                on_result(result)

        await asyncio.gather(*(run_one(src) for src in sources))

    finally:
        if owns_client:
            await active_client.aclose()

    return counts
