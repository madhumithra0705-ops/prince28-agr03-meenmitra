"""Check that DATABASE_URL in .env works.

Run:
    uv run python scripts/db_check.py
"""

import asyncio

from sqlalchemy import text

from meenmitra.config import get_settings
from meenmitra.db.session import make_engine


async def main() -> None:
    engine = make_engine(get_settings())

    try:
        async with engine.connect() as conn:
            version = await conn.scalar(text("SELECT version()"))
            database = await conn.scalar(text("SELECT current_database()"))

        print(f"Connected to database '{database}'")
        print(version)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
