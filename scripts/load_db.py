"""Load sample records into PostgreSQL with SHA-256 change detection."""

import asyncio
import hashlib
import json

from sqlalchemy import select

from meenmitra.config import get_settings
from meenmitra.db.models import Document
from meenmitra.db.session import make_engine, make_sessionmaker


async def main() -> None:
    settings = get_settings()
    records = json.loads(settings.data_file.read_text(encoding="utf-8"))

    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)

    inserted = 0
    updated = 0
    unchanged = 0

    try:
        async with sessionmaker() as session, session.begin():
            for record in records:
                fingerprint = hashlib.sha256(
                    json.dumps(
                        record,
                        sort_keys=True,
                        ensure_ascii=False,
                    ).encode("utf-8")
                ).hexdigest()

                result = await session.execute(select(Document).where(Document.id == record["id"]))
                document = result.scalar_one_or_none()

                if document is None:
                    document = Document(
                        id=record["id"],
                        species_scientific=record.get("species_scientific"),
                        local_name_tamil=record.get("local_name_tamil"),
                        english_name=record.get("english_name"),
                        topic=record.get("topic"),
                        region=record.get("region"),
                        regulation=record.get("regulation"),
                        source_url=record.get("source_url"),
                        sha256=fingerprint,
                        document_metadata={"sha256": fingerprint},
                    )
                    session.add(document)
                    inserted += 1

                elif document.sha256 == fingerprint:
                    unchanged += 1

                else:
                    document.species_scientific = record.get("species_scientific")
                    document.local_name_tamil = record.get("local_name_tamil")
                    document.english_name = record.get("english_name")
                    document.topic = record.get("topic")
                    document.region = record.get("region")
                    document.regulation = record.get("regulation")
                    document.source_url = record.get("source_url")
                    document.sha256 = fingerprint
                    document.document_metadata = {"sha256": fingerprint}
                    updated += 1

        print(f"records={len(records)} inserted={inserted} updated={updated} unchanged={unchanged}")

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
