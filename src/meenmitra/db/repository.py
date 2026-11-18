"""All SQL for documents lives here. Endpoints never write SQL themselves."""

import re
from typing import Any

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from meenmitra.db.models import Document

FILTER_KEY = re.compile(r"^[a-z_][a-z0-9_]{0,40}$")


def to_dict(doc: Document) -> dict[str, Any]:
    return {
        "id": doc.id,
        "species_scientific": doc.species_scientific,
        "local_name_tamil": doc.local_name_tamil,
        "english_name": doc.english_name,
        "topic": doc.topic,
        "region": doc.region,
        "regulation": doc.regulation,
        "source_url": doc.source_url,
        "doc_type": doc.doc_type,
        "sha256": doc.sha256,
        **(doc.document_metadata or {}),
    }


def _value_candidates(value: str) -> list[Any]:
    out: list[Any] = [value, [value]]
    lowered = value.lower()

    if lowered in ("true", "false"):
        out.append(lowered == "true")
    elif re.fullmatch(r"-?\d+", value):
        out.append(int(value))
    elif re.fullmatch(r"-?\d+\.\d+", value):
        out.append(float(value))

    return out


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        *,
        q: str | None,
        filters: dict[str, str],
        limit: int,
        offset: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        stmt = select(Document)

        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    Document.id.ilike(like),
                    Document.species_scientific.ilike(like),
                    Document.local_name_tamil.ilike(like),
                    Document.english_name.ilike(like),
                    Document.topic.ilike(like),
                    Document.region.ilike(like),
                    Document.regulation.ilike(like),
                    Document.source_url.ilike(like),
                    Document.doc_type.ilike(like),
                    Document.sha256.ilike(like),
                    cast(Document.document_metadata, Text).ilike(like),
                )
            )

        column_filters = {
            "id": Document.id,
            "species_scientific": Document.species_scientific,
            "local_name_tamil": Document.local_name_tamil,
            "english_name": Document.english_name,
            "topic": Document.topic,
            "region": Document.region,
            "regulation": Document.regulation,
            "source_url": Document.source_url,
            "doc_type": Document.doc_type,
            "sha256": Document.sha256,
        }

        for key, value in filters.items():
            column = column_filters.get(key)

            if column is not None:
                stmt = stmt.where(column == value)
            else:
                stmt = stmt.where(
                    or_(
                        *(
                            Document.document_metadata.contains({key: candidate})
                            for candidate in _value_candidates(value)
                        )
                    )
                )

        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))

        rows = await self.session.scalars(stmt.order_by(Document.id).limit(limit).offset(offset))

        return total or 0, [to_dict(doc) for doc in rows]

    async def get(self, external_id: str) -> dict[str, Any] | None:
        doc = await self.session.scalar(select(Document).where(Document.id == external_id))
        return to_dict(doc) if doc else None
