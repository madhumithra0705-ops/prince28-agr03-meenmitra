"""Measure the local MeenMitra corpus and generate dataset/capacity reports."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "manifest.jsonl"
CACHE = ROOT / "data" / "raw" / ".measured.json"
SOURCES = ROOT / "data" / "sources.csv"
DATASET = ROOT / "DATASET.md"
CAPACITY = ROOT / "docs" / "CAPACITY.md"

START_MARKER = "<!-- generated:start -->"
END_MARKER = "<!-- generated:end -->"

CHUNK_TOKENS = 700
OVERLAP_TOKENS = 100
EMBEDDING_USD_PER_MILLION = 0.15
VECTOR_DIMS = 768
USD_INR = 95


class VisibleText(HTMLParser):
    """Collect visible HTML text while ignoring scripts and styles."""

    def __init__(self) -> None:
        super().__init__()
        self.hidden_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.hidden_depth = max(0, self.hidden_depth - 1)

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            text = data.strip()
            if text:
                self.parts.append(text)


def load_records() -> list[dict]:
    if not MANIFEST.exists():
        raise SystemExit(f"Manifest not found: {MANIFEST}")

    records = []
    content = MANIFEST.read_text(encoding="utf-8")
    for line_number, line in enumerate(content.split("\n"), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSON in manifest at line {line_number}: {exc}") from exc
    return records


def load_source_licences() -> dict[str, str]:
    """Load source-level licence statements from sources.csv."""
    licences: dict[str, set[str]] = defaultdict(set)

    if not SOURCES.exists():
        return {}

    import csv

    with SOURCES.open(encoding="utf-8-sig", newline="") as source_file:
        reader = csv.DictReader(source_file)
        for row in reader:
            url = (row.get("url") or "").strip()
            licence = (row.get("licence") or "").strip()
            if url and licence:
                licences[url].add(licence)

    return {url: "; ".join(sorted(values)) for url, values in licences.items()}


def latest_downloads(records: list[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for record in records:
        url = record.get("url")
        if url:
            latest[url] = record

    result = []
    for record in latest.values():
        if record.get("status") != "downloaded" or not record.get("path"):
            continue
        path = ROOT / Path(record["path"])
        if path.is_file():
            result.append(record)
    return result


def read_visible_text(path: Path) -> str:
    if path.suffix.lower() in {".html", ".htm"}:
        parser = VisibleText()
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        return " ".join(parser.parts)

    if path.suffix.lower() in {".txt", ".md", ".rst", ".csv"}:
        return path.read_text(encoding="utf-8", errors="replace")

    return ""


def measure(record: dict, cache: dict) -> dict:
    path = ROOT / Path(record["path"])
    stat = path.stat()
    key = record.get("sha256") or str(path)
    cached = cache.get(key)

    if (
        cached
        and cached.get("bytes") == stat.st_size
        and cached.get("mtime_ns") == stat.st_mtime_ns
    ):
        return cached

    suffix = path.suffix.lower()
    pages = 0
    chars = 0
    method = "file size only"

    if suffix == ".pdf":
        try:
            reader = PdfReader(str(path))
            pages = len(reader.pages)
            chars = sum(len(page.extract_text() or "") for page in reader.pages)
            method = "PDF page count and extracted text"
        except Exception as exc:
            method = f"PDF measurement failed: {type(exc).__name__}"

    elif suffix in {".html", ".htm"}:
        text = read_visible_text(path)
        chars = len(text)
        pages = max(1, math.ceil(chars / 3000))
        method = "HTML visible text; 3,000 characters approximated as one page"

    elif suffix in {".txt", ".md", ".rst", ".csv"}:
        text = read_visible_text(path)
        chars = len(text)
        pages = max(1, math.ceil(chars / 3000))
        method = "Text characters; 3,000 characters approximated as one page"

    result = {
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "pages": pages,
        "chars": chars,
        "method": method,
    }
    cache[key] = result
    return result


def safe_cell(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def put_block(path: Path, generated: str) -> None:
    if not path.exists():
        raise SystemExit(f"Expected starter file does not exist: {path}")

    content = path.read_text(encoding="utf-8")
    if content.count(START_MARKER) != 1 or content.count(END_MARKER) != 1:
        raise SystemExit(f"Expected exactly one generated marker pair in {path}")

    start = content.index(START_MARKER) + len(START_MARKER)
    end = content.index(END_MARKER)
    if end < start:
        raise SystemExit(f"Generated markers are in the wrong order in {path}")

    updated = content[:start] + "\n\n" + generated.strip() + "\n\n" + content[end:]
    path.write_text(updated, encoding="utf-8")


def dataset_block(
    records: list[dict],
    measurements: list[dict],
    full_pages: int,
    source_licences: dict[str, str],
) -> str:
    grouped: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for record, measurement in zip(records, measurements, strict=False):
        grouped[record.get("source") or "unknown"].append((record, measurement))

    total_bytes = sum(item["bytes"] for item in measurements)
    total_pages = sum(item["pages"] for item in measurements)
    total_chars = sum(item["chars"] for item in measurements)

    lines = [
        f"*Generated: {datetime.now(UTC).isoformat()}*",
        "",
        "## Collected corpus summary",
        "",
        f"- Downloaded files present on disk: **{len(records)}**",
        f"- Total size: **{total_bytes / (1024 * 1024):,.2f} MiB**",
        f"- Estimated/measured pages: **{total_pages:,}**",
        f"- Extracted text: **{total_chars:,} characters**",
        f"- Full-corpus planning target: **{full_pages:,} pages**",
        "",
        "## Breakdown by source",
        "",
        (
            "| Source | Files | Size (MiB) | Pages | Licence | "
            "Measurement | Latest fetch | Example URL |"
        ),
        "|---|---:|---:|---:|---|---|---|---|",
    ]

    for source, items in sorted(grouped.items()):
        size = sum(m["bytes"] for _, m in items) / (1024 * 1024)
        pages = sum(m["pages"] for _, m in items)
        methods = sorted({m["method"] for _, m in items})
        dates = [r.get("timestamp") or r.get("fetched_at") or "" for r, _ in items]
        latest_date = max(dates, default="")
        example_url = items[0][0].get("url", "")
        method = "; ".join(methods)

        licence_values = sorted(
            {
                source_licences.get(r.get("url", ""), "").strip()
                or str(r.get("licence") or "").strip()
                for r, _ in items
            }
            - {""}
        )
        licence = "; ".join(licence_values) if licence_values else "Not recorded"

        lines.append(
            f"| {safe_cell(source)} | {len(items)} | {size:.2f} | "
            f"{pages} | {safe_cell(licence)} | {safe_cell(method)} | "
            f"{safe_cell(latest_date)} | {safe_cell(example_url)} |"
        )

    lines.extend(
        [
            "",
            "## Downloaded files",
            "",
            "The first 200 downloaded files currently present on disk:",
            "",
        ]
    )

    for record in sorted(records, key=lambda r: r.get("path", ""))[:200]:
        lines.append(f"- `{record.get('path', '')}`")

    if len(records) > 200:
        lines.append(f"- *{len(records) - 200} additional files omitted from this list.*")

    lines.extend(
        [
            "",
            "## Measurement notes",
            "",
            (
                "- PDF page counts come from the PDF reader; extracted text may be incomplete "
                "for scanned PDFs."
            ),
            "- HTML and plain-text page counts are estimates using 3,000 characters per page.",
            (
                "- Git repository Markdown files are included when their manifest status is "
                "downloaded and the local file exists."
            ),
            "- Only the latest manifest record for each URL is counted.",
            (
                "- Licence statements are source-level declarations from data/sources.csv "
                "or the manifest; they do not independently grant reuse rights."
            ),
        ]
    )
    return "\n".join(lines)


def capacity_block(measurements: list[dict], full_pages: int) -> str:
    current_pages = sum(item["pages"] for item in measurements)
    current_chars = sum(item["chars"] for item in measurements)
    current_files = len(measurements)

    chars_per_page = current_chars / current_pages if current_pages else 3000
    target_chars = int(full_pages * chars_per_page)
    target_tokens = target_chars / 4
    chunks = (
        max(0, math.ceil(target_tokens / (CHUNK_TOKENS - OVERLAP_TOKENS))) if target_tokens else 0
    )
    embedding_cost = target_tokens / 1_000_000 * EMBEDDING_USD_PER_MILLION
    vector_bytes = chunks * VECTOR_DIMS * 4
    text_bytes = target_chars * 1.2

    current_mib = sum(item["bytes"] for item in measurements) / (1024 * 1024)
    scale = full_pages / current_pages if current_pages else 0
    projected_mib = current_mib * scale if scale else 0

    return "\n".join(
        [
            f"*Generated: {datetime.now(UTC).isoformat()}*",
            "",
            "## Measured corpus and planning assumptions",
            "",
            f"- Current files measured: **{current_files:,}**",
            f"- Current measured/estimated pages: **{current_pages:,}**",
            f"- Current extracted text: **{current_chars:,} characters**",
            f"- Full target: **{full_pages:,} pages**",
            f"- Estimated target text: **{target_chars:,} characters**",
            f"- Estimated target tokens (4 characters/token): **{target_tokens:,.0f}**",
            f"- Chunk size / overlap: **{CHUNK_TOKENS} / {OVERLAP_TOKENS} tokens**",
            f"- Estimated chunks: **{chunks:,}**",
            "",
            "## Storage and embedding estimates",
            "",
            "| Measure | Estimate |",
            "|---|---:|",
            f"| Current downloaded files | {current_mib:,.2f} MiB |",
            f"| Projected raw corpus at target size | {projected_mib:,.2f} MiB |",
            (
                f"| Embedding API cost at ${EMBEDDING_USD_PER_MILLION:.2f}/million tokens | "
                f"${embedding_cost:,.4f} (about {embedding_cost * USD_INR:,.2f}) |"
            ),
            (
                f"| Vector storage ({VECTOR_DIMS} dimensions, float32) | "
                f"{vector_bytes / (1024 * 1024):,.2f} MiB |"
            ),
            (
                f"| Extracted text storage (1.2 bytes/character estimate) | "
                f"{text_bytes / (1024 * 1024):,.2f} MiB |"
            ),
            "",
            "## Limitations",
            "",
            (
                "- Page counts for HTML and text are character-based approximations, "
                "not printed-page counts."
            ),
            (
                "- The text estimate is based on extractable text in the current corpus; "
                "scanned PDFs may contain less text than their visual page count suggests."
            ),
            (
                "- Embedding price, vector dimensions, chunk size, overlap, and storage "
                "multipliers are planning assumptions, not measured provider bills."
            ),
            (
                "- Raw file projection assumes the current average file size remains "
                "representative as the corpus grows."
            ),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-pages", type=int, default=10000)
    args = parser.parse_args()

    if args.full_pages <= 0:
        raise SystemExit("--full-pages must be greater than zero")

    records = latest_downloads(load_records())
    source_licences = load_source_licences()
    CACHE.parent.mkdir(parents=True, exist_ok=True)

    try:
        cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    except (json.JSONDecodeError, OSError):
        cache = {}

    measurements = [measure(record, cache) for record in records]
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    DATASET.parent.mkdir(parents=True, exist_ok=True)
    CAPACITY.parent.mkdir(parents=True, exist_ok=True)

    put_block(
        DATASET,
        dataset_block(records, measurements, args.full_pages, source_licences),
    )
    put_block(CAPACITY, capacity_block(measurements, args.full_pages))

    total_bytes = sum(item["bytes"] for item in measurements)
    total_pages = sum(item["pages"] for item in measurements)
    print(f"Downloaded files measured: {len(records)}")
    print(f"Total size: {total_bytes / (1024 * 1024):.2f} MiB")
    print(f"Measured/estimated pages: {total_pages}")
    print(f"Full-corpus target: {args.full_pages} pages")
    print(f"Updated: {DATASET.relative_to(ROOT)}")
    print(f"Updated: {CAPACITY.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
