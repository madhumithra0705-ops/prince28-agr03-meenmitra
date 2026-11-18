import pytest
from fastapi.testclient import TestClient

from meenmitra.api.deps import check_db, get_repo
from meenmitra.api.main import create_app
from meenmitra.config import Settings

SAMPLE = [
    {
        "id": "001",
        "english_name": "Alpha guideline",
        "species_scientific": "Species alpha",
        "topic": "guideline",
        "region": "Chennai",
        "doc_type": "guideline",
        "kind": "guideline",
        "year": 2023,
        "sha256": "a" * 64,
    },
    {
        "id": "002",
        "english_name": "Beta circular",
        "species_scientific": "Species beta",
        "topic": "circular",
        "region": "Madurai",
        "doc_type": "circular",
        "kind": "circular",
        "year": 2024,
        "sha256": "b" * 64,
    },
    {
        "id": "003",
        "english_name": "Gamma notice",
        "species_scientific": "Species gamma",
        "topic": "notice",
        "region": "Chennai",
        "doc_type": "notice",
        "kind": "circular",
        "year": 2025,
        "sha256": "c" * 64,
    },
]


class FakeRepo:
    """Behaves like DocumentRepository without accessing PostgreSQL."""

    def __init__(self, rows):
        self.rows = rows

    async def list(self, *, q, filters, limit, offset):
        rows = [
            record
            for record in self.rows
            if (not q or q.lower() in str(record).lower())
            and all(str(record.get(key)) == value for key, value in filters.items())
        ]
        return len(rows), rows[offset : offset + limit]

    async def get(self, external_id):
        return next(
            (record for record in self.rows if record["id"] == external_id),
            None,
        )


@pytest.fixture
def settings():
    return Settings(
        app_env="ci",
        database_url="postgresql://localhost:5432/unused",
        _env_file=None,
    )


@pytest.fixture
def db_state():
    return {"up": True}


@pytest.fixture
def client(settings, db_state):
    app = create_app(settings)
    app.dependency_overrides[get_repo] = lambda: FakeRepo(SAMPLE)
    app.dependency_overrides[check_db] = lambda: db_state["up"]

    with TestClient(app) as test_client:
        yield test_client
