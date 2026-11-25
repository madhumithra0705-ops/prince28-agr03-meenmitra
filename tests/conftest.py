import pytest
from fastapi.testclient import TestClient

from meenmitra.api.deps import check_db, get_gateway, get_repo, get_usage_repo
from meenmitra.api.main import create_app
from meenmitra.config import Settings
from meenmitra.llm.gateway import FakeLLM, LLMGateway

# Tiny fake records: unit tests never touch a real database or your data file.
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
    # _env_file=None: ignore your local .env so tests behave the same everywhere
    return Settings(app_env="ci", database_url="postgresql://localhost:5432/unused", _env_file=None)


@pytest.fixture
def db_state():
    return {"up": True}


class FakeUsage:
    async def by_day(self, days=7):
        return [
            {
                "day": "2026-11-25",
                "calls": 3,
                "errors": 1,
                "fallbacks": 1,
                "tokens_in": 300,
                "tokens_out": 120,
                "cost_inr": 0.0642,
            }
        ]


@pytest.fixture
def llm():
    """The fake model behind /v1/chat in unit tests. Put strings or errors in llm.script."""
    return FakeLLM()


@pytest.fixture
def client(settings, db_state, llm):
    app = create_app(settings)
    app.dependency_overrides[get_repo] = lambda: FakeRepo(SAMPLE)
    app.dependency_overrides[check_db] = lambda: db_state["up"]
    app.dependency_overrides[get_gateway] = lambda: LLMGateway([llm])
    app.dependency_overrides[get_usage_repo] = lambda: FakeUsage()
    with TestClient(app) as c:
        yield c
