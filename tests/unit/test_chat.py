"""Tests for the chat and usage API endpoints."""

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from meenmitra.api.deps import get_gateway, get_usage_repo
from meenmitra.api.main import create_app
from meenmitra.config import Settings
from meenmitra.llm.gateway import LLMResult, LLMUnavailable


@dataclass
class FakeResult:
    text: str = "Fishing ban information"
    provider: str = "groq"
    model: str = "test-model"
    tokens_in: int = 10
    tokens_out: int = 8
    latency_ms: int = 100
    attempts: int = 1
    fallback_used: bool = False
    cost_inr: float = 0.01


class FakeGateway:
    async def generate(self, messages, **kwargs):
        return FakeResult()

    async def stream(self, messages, **kwargs):
        yield "Fishing "
        yield "ban information"
        yield LLMResult(
            text="Fishing ban information",
            provider="groq",
            model="test-model",
            tokens_in=10,
            tokens_out=8,
            latency_ms=100,
            attempts=1,
            fallback_used=False,
            cost_inr=0.01,
        )


class FakeUsage:
    async def by_day(self, days):
        return [
            {
                "day": "2026-11-25",
                "calls": 2,
                "cost_inr": 0.02,
            }
        ]


@pytest.fixture
def chat_client():
    settings = Settings(
        app_env="ci",
        database_url="postgresql://localhost:5432/unused",
        _env_file=None,
    )

    app = create_app(settings)
    app.dependency_overrides[get_gateway] = lambda: FakeGateway()
    app.dependency_overrides[get_usage_repo] = lambda: FakeUsage()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_chat_non_streaming(chat_client):
    response = chat_client.post(
        "/v1/chat",
        json={
            "message": "What is a fishing ban?",
            "stream": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Fishing ban information"
    assert response.json()["provider"] == "groq"
    assert "text" not in response.json()


def test_chat_streaming(chat_client):
    response = chat_client.post(
        "/v1/chat",
        json={
            "message": "What is a fishing ban?",
            "stream": True,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"delta": "Fishing "' in response.text
    assert '"delta": "ban information"' in response.text
    assert "event: done" in response.text


def test_chat_returns_503_when_model_unavailable(chat_client):
    async def unavailable(*args, **kwargs):
        raise LLMUnavailable("all providers failed")

    class BrokenGateway:
        generate = unavailable

        async def stream(self, *args, **kwargs):
            raise LLMUnavailable("all providers failed")
            yield

    chat_client.app.dependency_overrides[get_gateway] = lambda: BrokenGateway()

    response = chat_client.post(
        "/v1/chat",
        json={
            "message": "What is a fishing ban?",
            "stream": False,
        },
    )

    assert response.status_code == 503
    assert "all providers failed" in response.json()["detail"]


def test_usage_returns_daily_cost(chat_client):
    response = chat_client.get("/v1/usage")

    assert response.status_code == 200
    assert response.json()["calls"] == 2
    assert response.json()["total_cost_inr"] == 0.02
