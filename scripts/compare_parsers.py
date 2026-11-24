import argparse
import re
from pathlib import Path

import trafilatura
from bs4 import BeautifulSoup

from meenmitra.ingest.parse import (
    parse_file,
    parse_pdf_pymupdf,
    parse_pdf_pypdf,
)

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "NOTES.md"

START = "<!-- BEGIN PARSER COMPARISON -->"
END = "<!-- END PARSER COMPARISON -->"


def text_stats(text, pages=None):
    return {
        "chars": len(text),
        "pages": pages,
        "preview": re.sub(r"\s+", " ", text).strip()[:160],
        "error": None,
    }


def parsed_stats(parsed):
    text = "\n".join(page.text for page in parsed.pages)
    return text_stats(text, len(parsed.pages))


def run_safely(function):
    try:
        return function()
    except Exception as exc:
        return {
            "chars": None,
            "pages": None,
            "preview": "",
            "error": f"{type(exc).__name__}: {str(exc)[:100]}",
        }


def compare_pdf(path):
    first = run_safely(lambda: parsed_stats(parse_pdf_pymupdf(path)))
    second = run_safely(lambda: parsed_stats(parse_pdf_pypdf(path)))
    return "PDF", "PyMuPDF", first, "pypdf", second


def compare_html(path):
    raw = path.read_text(encoding="utf-8", errors="replace")

    first = run_safely(
        lambda: text_stats(
            trafilatura.extract(
                raw,
                output_format="markdown",
                include_tables=True,
                include_links=False,
                include_comments=False,
                favor_precision=True,
            )
            or ""
        )
    )

    def strip_tags():
        soup = BeautifulSoup(raw, "html.parser")
        for element in soup(["script", "style", "noscript"]):
            element.decompose()
        return text_stats(soup.get_text(" ", strip=True))

    second = run_safely(strip_tags)

    return "HTML", "Trafilatura", first, "BeautifulSoup tag-strip", second


def compare_single(path):
    result = run_safely(lambda: parsed_stats(parse_file(path)))
    parser_name = "single: parse_file"
    return path.suffix.lstrip(".").upper(), parser_name, result, "—", None


def display_stats(result):
    if result is None:
        return "—"
    if result["error"]:
        return "ERROR: " + result["error"]
    value = f"{result['chars']:,} chars"
    if result["pages"] is not None:
        value += f", {result['pages']} pages"
    return value


def markdown_cell(value):
    return str(value or "—").replace("|", "\\|").replace("\n", " ")


def display_preview(result):
    if result is None:
        return "—"
    if result["error"]:
        return result["error"]
    preview = result["preview"] or "[No text extracted]"
    return markdown_cell(preview)


def relative_path(path):
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def main():
    parser = argparse.ArgumentParser(
        description="Compare PDF and HTML parsers on selected raw files."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files to compare. Without paths, selects the 10 largest PDF/HTML files.",
    )
    args = parser.parse_args()

    if args.paths:
        paths = [
            (Path(value) if Path(value).is_absolute() else ROOT / value).resolve()
            for value in args.paths
        ]
    else:
        raw_dir = ROOT / "data" / "raw"
        paths = sorted(
            (
                path
                for path in raw_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in {".pdf", ".html", ".htm"}
            ),
            key=lambda path: path.stat().st_size,
            reverse=True,
        )[:10]

    if not paths:
        parser.error("No comparison files were found.")

    missing = [path for path in paths if not path.is_file()]
    if missing:
        for path in missing:
            print(f"MISSING: {path}")
        raise SystemExit(1)

    rows = []

    for path in paths:
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            kind, name_a, result_a, name_b, result_b = compare_pdf(path)
        elif suffix in {".html", ".htm"}:
            kind, name_a, result_a, name_b, result_b = compare_html(path)
        else:
            kind, name_a, result_a, name_b, result_b = compare_single(path)

        rows.append(
            f"| {markdown_cell(relative_path(path))} "
            f"| {kind} "
            f"| {name_a} "
            f"| {display_stats(result_a)} "
            f"| {display_preview(result_a)} "
            f"| {name_b} "
            f"| {display_stats(result_b)} "
            f"| {display_preview(result_b)} |"
        )

        print(f"\n{relative_path(path)}")
        print(f"  {name_a}: {display_stats(result_a)}")
        print(f"  {name_b}: {display_stats(result_b)}")

    block = "\n".join(
        [
            START,
            "## Parser comparison — difficult files",
            "",
            "| File | Type | Parser A | A output | A preview | Parser B | B output | B preview |",
            "|---|---|---|---:|---|---|---:|---|",
            *rows,
            "",
            f"Compared files: {len(paths)}",
            END,
        ]
    )

    notes = NOTES.read_text(encoding="utf-8") if NOTES.exists() else ""

    if START in notes and END in notes:
        start = notes.index(START)
        end = notes.index(END, start) + len(END)
        notes = notes[:start] + block + notes[end:]
    elif START in notes or END in notes:
        raise SystemExit("NOTES.md has an incomplete comparison marker. No changes made.")
    else:
        notes = notes.rstrip() + "\n\n" + block + "\n"

    NOTES.write_text(notes, encoding="utf-8")

    print(f"\ncompared {len(paths)} files -> table written to NOTES.md")


if __name__ == "__main__":
    main()
