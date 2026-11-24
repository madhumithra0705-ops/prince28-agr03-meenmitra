"""Turn one raw file into clean pages.

No database here: a file goes in, and either a ParsedDoc comes out or a
ParseError with a reason. Every page keeps its page number and the section
path it starts in, because answers will cite "document, page, section".
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
import trafilatura
from bs4 import BeautifulSoup
from pypdf import PdfReader

TEXT_TYPES = {".md", ".mdx", ".markdown", ".txt", ".rst", ".adoc", ".sgml", ".py"}
DATA_TYPES = {".json", ".yaml", ".yml", ".csv", ".xml"}
PAGE_CHARS = 3000
MIN_CHARS_PER_PAGE = 50


@dataclass
class ParsedPage:
    page_no: int
    text: str
    headings: list[str] = field(default_factory=list)
    tables: int = 0


@dataclass
class ParsedDoc:
    parser: str
    kind: str
    title: str
    pages: list[ParsedPage]


class ParseError(Exception):
    """A file we could not parse, with a short machine-readable reason."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail[:500]


# ---------- cleaning ----------


def clean_text(text: str) -> str:
    """Apply consistent text repairs for every parser."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\x00", "").replace("\u00ad", "")
    text = re.sub(r"(?<=[a-z])-\n(?=[a-z])", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def drop_repeated_lines(pages: list[str]) -> list[str]:
    """Remove repeated headers and footers from page edges."""
    if len(pages) < 4:
        return pages

    def key(line: str) -> str:
        return re.sub(r"\d+", "#", line.strip().lower())

    seen: Counter[str] = Counter()

    for page in pages:
        lines = [line for line in page.splitlines() if line.strip()]
        seen.update(
            key(line) for line in lines[:2] + lines[-2:] if not line.lstrip().startswith("#")
        )

    repeated = {value for value, count in seen.items() if count >= 0.6 * len(pages)}

    cleaned = []

    for page in pages:
        lines = page.splitlines()
        nonempty = [i for i, line in enumerate(lines) if line.strip()]
        edge = set(nonempty[:2] + nonempty[-2:])

        cleaned.append(
            "\n".join(
                line for i, line in enumerate(lines) if not (i in edge and key(line) in repeated)
            )
        )

    return cleaned


# ---------- headings ----------

HEADING = re.compile(r"^(#{1,6}) +(.+?)\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")


def heading_title(raw: str) -> str:
    """Remove trailing Markdown heading anchors."""
    return re.sub(r"\s+\{\s*[#.][^}]+\}\s*$", "", raw).strip()


def headings_in(
    text: str,
    in_code: bool = False,
) -> tuple[list[tuple[int, str]], bool]:
    """Find Markdown headings while ignoring fenced code blocks."""
    found = []

    for line in text.splitlines():
        if FENCE.match(line):
            in_code = not in_code
        elif not in_code and (match := HEADING.match(line)):
            title = heading_title(match.group(2))
            if title:
                found.append((len(match.group(1)), title))

    return found, in_code


def with_heading_paths(texts: list[str]) -> list[ParsedPage]:
    """Remember the active section path at the start of every page."""
    pages = []
    path = []
    in_code = False

    for number, text in enumerate(texts, start=1):
        pages.append(
            ParsedPage(
                page_no=number,
                text=text,
                headings=list(path),
                tables=text.count("\n|---"),
            )
        )

        found, in_code = headings_in(text, in_code)

        for level, title in found:
            path = path[: level - 1] + [title]

    return pages


def finish(
    parser: str,
    kind: str,
    title: str,
    texts: list[str],
) -> ParsedDoc:
    """Clean pages and create the final parsed document."""
    texts = drop_repeated_lines([clean_text(text) for text in texts])
    texts = [clean_text(text) for text in texts]

    if not any(texts):
        raise ParseError("empty", "no text after cleaning")

    found, _ = headings_in("\n".join(texts))

    document_title = title.strip() or (found[0][1] if found else "")

    return ParsedDoc(
        parser=parser,
        kind=kind,
        title=document_title,
        pages=with_heading_paths(texts),
    )


# ---------- PDF title and heading helpers ----------

PDF_NOISE_HEADINGS = {
    "EXTRAORDINARY",
    "PUBLISHED BY AUTHORITY",
    "TAMIL NADU",
    "GOVERNMENT GAZETTE",
    "TAMIL NADU GOVERNMENT GAZETTE",
    "TAMIL NADU GOVERNMENT GAZETTE EXTRAORDINARY",
    "NOTIFICATIONS BY GOVERNMENT",
}

PDF_MASTHEAD_LINES = {
    "GENERAL STATUTORY RULES, NOTIFICATIONS, ORDERS, REGULATIONS, ETC.,",
    "ISSUED BY SECRETARIAT DEPARTMENTS.",
    "ANIMAL HUSBANDRY, DAIRYING AND FISHERIES DEPARTMENT",
}


def _is_pdf_noise(text: str) -> bool:
    """Identify common gazette headers, page labels, and price lines."""
    value = re.sub(r"\s+", " ", text).strip()
    upper = value.upper()

    if not value:
        return True

    if upper in PDF_NOISE_HEADINGS:
        return True

    if re.match(r"^\[?\s*PRICE\s*:", upper):
        return True

    if re.match(r"^NO\.\s*\d+\]?$", upper):
        return True

    if re.match(r"^\[?\s*(REGD\.|R\. DIS\.)", upper):
        return True

    if "GOVERNMENT GAZETTE EXTRAORDINARY" in upper:
        return True

    return bool(
        re.match(
            r"^CHENNAI,\s+(MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY)",
            upper,
        )
    )


def _is_pdf_heading_noise(text: str) -> bool:
    """Identify Gazette masthead and date lines that are content, not sections."""
    value = re.sub(r"\s+", " ", text).strip()
    upper = value.upper()

    if upper in PDF_MASTHEAD_LINES:
        return True

    if re.match(r"^PART\s+III\s*[—–-]\s*SECTION\b", upper):
        return True

    return bool(re.match(r"^MAASI\s+\d+,\s+.*THIRUVALLUVAR\s+AANDU-\d+$", upper))


def _pdf_title(doc: pymupdf.Document) -> str:
    """Prefer the actual document title over generic PDF metadata."""
    metadata_title = (doc.metadata or {}).get("title", "").strip()

    normalized_metadata = metadata_title.casefold()
    generic_metadata = normalized_metadata in {
        "powerpoint presentation",
        "microsoft word",
        "microsoft powerpoint",
        "presentation",
        "document",
        "untitled",
        "untitled document",
    } or normalized_metadata.endswith((".pdf", ".indd", ".doc", ".docx", ".ppt", ".pptx"))

    if metadata_title and not generic_metadata:
        if not re.fullmatch(r"[\\w\\s().-]+", metadata_title):
            return metadata_title

        if (
            not re.search(r"\\b(final|copy|scan|document)\\b", metadata_title, re.I)
            and len(metadata_title) > 20
            and not re.search(r"\\d{4,}", metadata_title)
        ):
            return metadata_title

    if not doc.page_count:
        return "" if generic_metadata else metadata_title

    # Preserve the existing Gazette title detection.
    candidates = []

    for line in doc[0].get_text().splitlines():
        value = re.sub(r"\\s+", " ", line).strip()

        if len(value) < 12 or len(value) > 220:
            continue
        if _is_pdf_noise(value) or value != value.upper():
            continue

        if re.search(
            r"\\b(RULES|ACT|GUIDELINES|POLICY|SCHEME|REPORT|REGULATION)\\b",
            value,
        ):
            candidates.append(value)

    if candidates:
        return max(candidates, key=len).strip(" .")

    # Check the first six pages for prominent cover titles.
    page_lines = []

    for page in list(doc)[:6]:
        lines = []

        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue

            for line in block.get("lines", []):
                spans = line.get("spans", [])
                value = re.sub(
                    r"\\s+",
                    " ",
                    "".join(span.get("text", "") for span in spans),
                ).strip()

                if len(value) < 12 or len(value) > 220 or _is_pdf_noise(value):
                    continue

                lines.append(
                    {
                        "text": value,
                        "size": max(
                            (float(span.get("size", 0)) for span in spans),
                            default=0,
                        ),
                        "bold": any(span.get("flags", 0) & 16 for span in spans),
                    }
                )

        page_lines.append(lines)

    for lines in page_lines:
        prominent = [line for line in lines if line["size"] >= 30]
        if prominent:
            return " ".join(line["text"] for line in prominent)

    for lines in page_lines:
        prominent = [
            line
            for line in lines
            if line["bold"] and line["size"] >= 18 and line["text"] == line["text"].upper()
        ]

        if prominent:
            largest_size = max(line["size"] for line in prominent)
            title_lines = [
                line["text"] for line in prominent if abs(line["size"] - largest_size) <= 0.5
            ]
            return " ".join(title_lines)

    return "" if generic_metadata else metadata_title


def _body_size(doc: pymupdf.Document) -> float:
    """Find the most common font size, weighted by character count."""
    sizes: Counter[float] = Counter()

    for page in list(doc)[:30]:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    sizes[round(span["size"], 1)] += len(span["text"])

    return sizes.most_common(1)[0][0] if sizes else 10.0


def _heading_level(
    text: str,
    size: float,
    bold: bool,
    body: float,
) -> int:
    """Infer a conservative Markdown heading level from PDF typography."""
    value = re.sub(r"\s+", " ", text).strip()

    if not 2 < len(value) <= 120:
        return 0

    if not any(char.isalpha() for char in value):
        return 0

    if _is_pdf_noise(value) or _is_pdf_heading_noise(value):
        return 0

    # A new chapter resets the section path. It must be a top-level
    # heading so the previous chapter is not retained in later page paths.
    if re.fullmatch(r"CHAPTER\s+[IVXLCDM]+", value, re.I):
        return 1

    if size >= body * 1.6:
        return 1

    if size >= body * 1.3:
        return 2

    if size >= body * 1.12:
        return 3

    if (
        bold
        and len(value) <= 80
        and not value.endswith((".", ",", ";", ":"))
        and not re.match(r"^\(?\d+[\).]?$", value)
    ):
        return 2

    return 0


# ---------- PDF, parser 1: PyMuPDF ----------


def _open_pdf(path: Path) -> pymupdf.Document:
    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise ParseError("corrupt", str(exc)) from exc

    if doc.needs_pass:
        raise ParseError("encrypted", "the PDF needs a password")

    if doc.page_count == 0:
        raise ParseError("empty", "the PDF has no pages")

    return doc


def parse_pdf_pymupdf(path: Path) -> ParsedDoc:
    doc = _open_pdf(path)
    body = _body_size(doc)

    texts = []
    chars = 0

    for _page_number, page in enumerate(doc):
        tables = list(page.find_tables().tables) if len(page.get_cdrawings()) >= 4 else []

        used: set[int] = set()
        out = []

        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue

            rect = pymupdf.Rect(block["bbox"])

            inside = next(
                (i for i, table in enumerate(tables) if rect.intersects(table.bbox)),
                None,
            )

            if inside is not None:
                if inside not in used:
                    used.add(inside)
                    out.append("\n" + tables[inside].to_markdown().strip() + "\n")
                continue

            for line in block["lines"]:
                text = "".join(span["text"] for span in line["spans"]).strip()

                if not text:
                    continue

                # Remove common gazette banners and page furniture.
                if _is_pdf_noise(text):
                    continue

                # A page number by itself is not document content.
                if re.fullmatch(r"\[?\s*\d{1,4}\s*\]?", text):
                    continue

                size = max(span["size"] for span in line["spans"])
                bold = all(span["flags"] & 16 for span in line["spans"])

                level = _heading_level(text, size, bold, body)

                out.append(f"{'#' * level} {text}" if level else text)
                chars += len(text)

            out.append("")

        texts.append("\n".join(out))

    if chars < MIN_CHARS_PER_PAGE * len(texts):
        raise ParseError(
            "no_text_layer",
            f"{chars} characters on {len(texts)} pages: needs OCR",
        )

    return finish(
        "pymupdf",
        "pdf",
        _pdf_title(doc),
        texts,
    )


def parse_pdf_ocr(
    path: Path,
    language: str = "eng",
) -> ParsedDoc:
    """For scanned PDFs: use Tesseract OCR, which must be installed."""
    doc = _open_pdf(path)

    try:
        texts = [
            page.get_text(
                textpage=page.get_textpage_ocr(
                    language=language,
                    dpi=200,
                    full=True,
                )
            )
            for page in doc
        ]
    except Exception as exc:
        raise ParseError("ocr_unavailable", str(exc)) from exc

    return finish(
        f"ocr-{language}",
        "pdf",
        _pdf_title(doc),
        texts,
    )


# ---------- PDF, parser 2: pypdf ----------


def parse_pdf_pypdf(path: Path) -> ParsedDoc:
    try:
        reader = PdfReader(path)

        if reader.is_encrypted and not reader.decrypt(""):
            raise ParseError("encrypted", "the PDF needs a password")

        texts = [page.extract_text() or "" for page in reader.pages]

    except ParseError:
        raise
    except Exception as exc:
        raise ParseError("corrupt", str(exc)) from exc

    if not texts:
        raise ParseError("empty", "the PDF has no pages")

    if sum(len(text) for text in texts) < MIN_CHARS_PER_PAGE * len(texts):
        raise ParseError(
            "no_text_layer",
            f"almost no text on {len(texts)} pages: needs OCR",
        )

    metadata = reader.metadata
    title = str(metadata.title or "") if metadata else ""

    return finish(
        "pypdf",
        "pdf",
        title,
        texts,
    )


# ---------- HTML ----------


def _remove_repository_noise(main) -> None:
    """Remove CMFRI repository controls and descriptive metadata."""
    for element in main.select(
        "script, style, nav, footer, .ep_document_citation, .ep_summary_page_actions"
    ):
        element.decompose()

    for link in main.select("a.ep_document_link"):
        table = link.find_parent("table")
        if table:
            table.decompose()

    metadata_labels = {
        "item type",
        "uncontrolled keywords",
        "subjects",
        "divisions",
        "depositing user",
        "date deposited",
        "last modified",
        "uri",
    }

    for table in main.find_all("table"):
        labels = {
            cell.get_text(" ", strip=True).rstrip(":").lower()
            for cell in table.find_all(["th", "td"])
        }

        if labels.intersection(metadata_labels):
            table.decompose()

    for heading in main.find_all(["h2", "h3", "h4"]):
        if heading.get_text(" ", strip=True).lower().startswith("actions"):
            for sibling in list(heading.find_all_next()):
                if sibling.name in {"h2", "h3", "h4"}:
                    break
                sibling.decompose()

            heading.decompose()

    for element in list(main.find_all("div")):
        if "official url:" in element.get_text(" ", strip=True).lower():
            element.decompose()


def _remove_html_citation_before_abstract(main) -> None:
    """Remove repository citation material before the Abstract section."""
    abstract = None

    for heading in main.find_all(["h1", "h2", "h3", "h4"]):
        if heading.get_text(" ", strip=True).lower() == "abstract":
            abstract = heading
            break

    if abstract is None:
        return

    for sibling in list(abstract.find_previous_siblings()):
        sibling.decompose()


def _html_to_markdown(main) -> str:
    """Convert article blocks to Markdown while preserving section headings."""
    output = []

    for element in main.find_all(
        ["h1", "h2", "h3", "h4", "h5", "h6", "p", "pre", "blockquote", "li"]
    ):
        if element.find_parent(["li", "pre", "blockquote"]):
            continue

        text = element.get_text(" ", strip=True)

        if not text:
            continue

        if element.name.startswith("h"):
            level = int(element.name[1])
            output.append(f"{'#' * level} {text}")
        elif element.name == "pre":
            output.append(f"```\n{text}\n```")
        elif element.name == "blockquote":
            output.append("\n".join(f"> {line}" for line in text.splitlines()))
        elif element.name == "li":
            output.append(f"- {text}")
        else:
            output.append(text)

    # Preserve article tables, but skip repository metadata tables.
    for table in main.find_all("table"):
        rows = []

        for row in table.find_all("tr"):
            cells = [
                cell.get_text(" ", strip=True).replace("|", "\\|")
                for cell in row.find_all(["th", "td"])
            ]

            if cells:
                rows.append(cells)

        if rows:
            width = max(len(row) for row in rows)
            rows = [row + [""] * (width - len(row)) for row in rows]

            markdown_rows = ["| " + " | ".join(row) + " |" for row in rows]

            if len(rows) > 1:
                separator = "| " + " | ".join(["---"] * width) + " |"
                markdown_rows.insert(1, separator)

            output.extend(markdown_rows)

    return "\n\n".join(output)


def parse_html(path: Path) -> ParsedDoc:
    html = path.read_text(
        encoding="utf-8",
        errors="replace",
    )
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("meta", attrs={"name": "DC.title"})
    title = title_tag.get("content", "").strip() if title_tag else ""

    if not title:
        title_tag = soup.find(
            "h1",
            class_="ep_tm_pagetitle",
        )
        title = title_tag.get_text(" ", strip=True) if title_tag else ""

    if not title:
        title_tag = soup.find("title")
        title = title_tag.get_text(" ", strip=True) if title_tag else ""

    main = soup.select_one(".ep_summary_content_main")

    if main is None:
        main = soup.select_one(".ep_tm_page_content")

    # Tamil Nadu Fisheries pages: select the actual article section.
    if main is None:
        main = soup.select_one("section.sidemenu section.faq")

    if main is None:
        main = soup.body or soup
    _remove_repository_noise(main)
    _remove_html_citation_before_abstract(main)

    markdown = _html_to_markdown(main)

    # Use Trafilatura as a fallback for pages without normal article blocks.
    if not markdown or len(markdown.strip()) < 40:
        markdown = (
            trafilatura.extract(
                str(main),
                output_format="markdown",
                include_tables=True,
                include_links=False,
                include_comments=False,
                favor_precision=True,
            )
            or ""
        )

    if not markdown or len(markdown.strip()) < 40:
        raise ParseError(
            "empty",
            "no main content found (a page built by JavaScript?)",
        )

    return finish(
        "beautifulsoup",
        "html",
        title,
        split_pages(markdown),
    )


# ---------- text files ----------

RST_MARKS = {
    "=": 1,
    "-": 2,
    "~": 3,
    "^": 3,
    '"': 3,
}


def markup_to_markdown(
    text: str,
    suffix: str,
) -> str:
    """Rewrite reStructuredText and AsciiDoc headings as Markdown headings."""
    lines = text.splitlines()

    if suffix == ".adoc":
        return "\n".join(
            re.sub(
                r"^(=+) ",
                lambda match: "#" * len(match.group(1)) + " ",
                line,
            )
            for line in lines
        )

    if suffix not in {".rst", ".txt"}:
        return text

    output = []

    for i, line in enumerate(lines):
        underline = lines[i + 1] if i + 1 < len(lines) else ""

        is_rule = len(underline) >= 3 and len(set(underline)) == 1 and underline[0] in RST_MARKS

        if line.strip() and is_rule and len(underline) >= len(line.rstrip()):
            output.append("#" * RST_MARKS[underline[0]] + " " + line.strip())
        elif not (output and len(line) >= 3 and len(set(line)) == 1 and line[0] in RST_MARKS):
            output.append(line)

    return "\n".join(output)


def split_pages(
    text: str,
    size: int = PAGE_CHARS,
) -> list[str]:
    """Split text into pages near paragraph boundaries."""
    pages = []
    current = []
    length = 0

    for paragraph in re.split(r"\n\s*\n", text):
        if current and length + len(paragraph) > size:
            pages.append("\n\n".join(current))
            current = []
            length = 0

        current.append(paragraph)
        length += len(paragraph)

    if current:
        pages.append("\n\n".join(current))

    return pages


def parse_text(path: Path) -> ParsedDoc:
    suffix = path.suffix.lower()
    text = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    if suffix in DATA_TYPES:
        return finish(
            "plain",
            "data",
            path.stem,
            split_pages(text),
        )

    return finish(
        "plain",
        "text",
        path.stem if suffix == ".py" else "",
        split_pages(markup_to_markdown(text, suffix)),
    )


# ---------- dispatcher ----------

PDF_PARSERS = {
    "pymupdf": parse_pdf_pymupdf,
    "pypdf": parse_pdf_pypdf,
}


def parse_file(
    path: Path,
    pdf_parser: str = "pymupdf",
) -> ParsedDoc:
    """Pick the parser by file type. Raises ParseError, never anything else."""
    suffix = path.suffix.lower()

    try:
        if suffix == ".pdf":
            parser = PDF_PARSERS.get(pdf_parser)

            if parser is None:
                raise ParseError(
                    "unsupported_parser",
                    pdf_parser,
                )

            return parser(path)

        if suffix in {".html", ".htm"}:
            return parse_html(path)

        if suffix in TEXT_TYPES | DATA_TYPES:
            return parse_text(path)

    except ParseError:
        raise
    except Exception as exc:
        raise ParseError(
            "crash",
            f"{type(exc).__name__}: {exc}",
        ) from exc

    raise ParseError(
        "unsupported_type",
        suffix or "no file extension",
    )
