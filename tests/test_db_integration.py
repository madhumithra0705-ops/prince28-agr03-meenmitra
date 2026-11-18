"""Integration tests against a separate, disposable PostgreSQL database."""

import asyncio
import os

import pytest
from fastapi.testclient import TestClient

from meenmitra.api.main import create_app
from meenmitra.config import Settings
from meenmitra.db.models import Base, Document
from meenmitra.db.session import make_engine, make_sessionmaker

TEST_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_URL,
    reason="set TEST_DATABASE_URL to run integration tests",
)


async def reset_and_seed(settings: Settings) -> None:
    engine = make_engine(settings)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        async with make_sessionmaker(engine)() as session, session.begin():
            session.add_all(
                [
                    Document(
                        id="001",
                        english_name="Alpha",
                        species_scientific="Species alpha",
                        doc_type="guideline",
                        sha256="a" * 64,
                        document_metadata={"kind": "guideline"},
                    ),
                    Document(
                        id="002",
                        english_name="Beta",
                        species_scientific="Species beta",
                        doc_type="circular",
                        sha256="b" * 64,
                        document_metadata={"kind": "circular"},
                    ),
                ]
            )
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def db_client():
    settings = Settings(
        app_env="ci",
        database_url=TEST_URL,
        _env_file=None,
    )

    asyncio.run(reset_and_seed(settings))

    with TestClient(create_app(settings)) as client:
        yield client


def test_ready_with_real_database(db_client):
    response = db_client.get("/ready")

    assert response.status_code == 200
    assert response.json()["checks"]["database"] is True


def test_filter_uses_jsonb_containment(db_client):
    response = db_client.get("/v1/documents", params={"kind": "circular"})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["002"]


def test_get_from_real_database(db_client):
    response = db_client.get("/v1/documents/001")

    assert response.status_code == 200
    assert response.json()["english_name"] == "Alpha"
    assert response.json()["sha256"] == "a" * 64


def test_filter_by_sha256_with_real_database(db_client):
    response = db_client.get(
        "/v1/documents",
        params={"sha256": "b" * 64},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["002"]
