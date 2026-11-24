"""Persist parsed documents and parse failures."""

from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from meenmitra.db.models import Document, Page, ParseFailure
from meenmitra.ingest.parse import ParsedDoc, ParseError


def document_id(sha256: str) -> str:
    """Create a stable document ID from the file hash."""
    return f"f-{sha256[:20]}"


async def parsed_ids(session: AsyncSession) -> set[str]:
    """Return IDs of documents that have already been parsed."""
    result = await session.scalars(
        select(Document.external_id).where(Document.doc_type != "record")
    )
    return set(result.all())


async def failed_paths(session: AsyncSession) -> set[str]:
    """Return paths already recorded in the parse-failure table."""
    result = await session.scalars(select(ParseFailure.path))
    return set(result.all())


async def save_document(
    session: AsyncSession,
    record: dict,
    parsed: ParsedDoc,
) -> None:
    """Save a parsed document and its pages; remove any old failure record."""
    path = str(record["path"])
    sha256 = record["sha256"]

    title = parsed.title or record.get("title") or Path(path).stem

    pages = [
        Page(
            page_number=page.page_no,
            content=page.text,
            headings=page.headings,
        )
        for page in parsed.pages
    ]

    document = Document(
        id=document_id(sha256),
        title=title[:500],
        source_url=record.get("url"),
        licence=(record.get("licence") or "")[:200],
        doc_type=parsed.kind,
        sha256=sha256,
        document_metadata={
            "source": record.get("source"),
            "path": path,
            "parser": parsed.parser,
            "pages": len(parsed.pages),
            "tables": sum(page.tables for page in parsed.pages),
            "chars": sum(len(page.text) for page in parsed.pages),
        },
        pages=pages,
    )

    await session.execute(delete(ParseFailure).where(ParseFailure.path == path))
    session.add(document)
    await session.commit()


async def save_failure(
    session: AsyncSession,
    record: dict,
    error: ParseError,
) -> None:
    """Insert a parse failure or update its reason and attempt count."""
    path = str(record["path"])

    statement = insert(ParseFailure).values(
        path=path,
        sha256=record["sha256"],
        source_url=record.get("url"),
        reason=error.reason,
        detail=error.detail,
        attempts=1,
    )

    statement = statement.on_conflict_do_update(
        index_elements=[ParseFailure.path],
        set_={
            "reason": error.reason,
            "detail": error.detail,
            "attempts": ParseFailure.attempts + 1,
        },
    )

    await session.execute(statement)
    await session.commit()
