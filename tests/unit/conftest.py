import pytest
from fastapi.testclient import TestClient

from meenmitra.api.deps import check_db, get_repo
from meenmitra.api.main import create_app
from meenmitra.config import Settings

SAMPLE = [
    {
        "id": "001",
        "english_name": "Alpha guideline",
        "local_name_tamil": "Alpha",
        "species_scientific": "Alpha species",
        "topic": "guideline",
        "region": "Chennai",
        "doc_type": "guideline",
        "year": 2023,
        "sha256": "a" * 64,
    },
    {
        "id": "002",
        "english_name": "Beta circular",
        "local_name_tamil": "Beta",
        "species_scientific": "Beta species",
        "topic": "circular",
        "kind": "circular",
        "region": "Madurai",
        "doc_type": "circular",
        "year": 2024,
        "sha256": "b" * 64,
    },
    {
        "id": "003",
        "english_name": "Gamma notice",
        "local_name_tamil": "Gamma",
        "species_scientific": "Gamma species",
        "topic": "notice",
        "region": "Chennai",
        "doc_type": "notice",
        "kind": "circular",
        "year": 2025,
        "sha256": "c" * 64,
    },
]


class FakeRepo:
    def __init__(self, rows):
        self.rows = rows

    async def list(self, *, q, filters, limit, offset):
        rows = self.rows

        if q:
            rows = [row for row in rows if q.lower() in row["english_name"].lower()]

        for key, value in filters.items():
            rows = [row for row in rows if str(row.get(key, "")).lower() == str(value).lower()]

        return len(rows), rows[offset : offset + limit]

    async def get(self, external_id):
        return next(
            (row for row in self.rows if row["id"] == external_id),
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

    app.dependency_overrides.clear()
