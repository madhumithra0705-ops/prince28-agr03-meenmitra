"""/v1/chat and /v1/usage, with the fake model from tests/conftest.py."""

import json

from meenmitra.llm.gateway import LLMError


def events(body: str) -> list[tuple[str, dict]]:
    """Parse a server-sent-event body into (event name, data) pairs."""
    out = []
    for block in body.strip().split("\n\n"):
        name = ""
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                out.append((name, json.loads(line[5:])))
    return out


def test_chat_without_streaming_returns_json(client, llm):
    llm.script = ["docs", "Use curly braces in the path."]
    r = client.post(
        "/v1/chat", json={"message": "How do I declare a path parameter?", "stream": False}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Use curly braces in the path."
    assert body["provider"] == "fake" and body["tokens_out"] == 6 and "cost_inr" in body
    assert llm.calls == 2


def test_chat_streams_pieces_and_ends_with_a_done_event(client, llm):
    llm.script = ["docs", "Use curly braces in the path."]
    r = client.post("/v1/chat", json={"message": "How do I declare a path parameter?"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    received = events(r.text)
    text = "".join(data["delta"] for name, data in received if name == "")
    assert text.strip() == "Use curly braces in the path."
    assert received[-1][0] == "done" and received[-1][1]["model"] == "fake-1"
    assert llm.calls == 2


def test_personal_question_returns_fixed_answer_without_chat_call(client, llm):
    llm.script = ["personal"]
    r = client.post(
        "/v1/chat",
        json={"message": "Will there be good catch near Dhanushkodi tomorrow?"},
    )
    assert r.status_code == 200
    received = events(r.text)
    assert received[0][1]["delta"] == "I can't know that."
    assert received[-1] == ("done", {"answer": "I can't know that."})
    assert llm.calls == 1


def test_off_topic_question_returns_fixed_answer_without_chat_call(client, llm):
    llm.script = ["off_topic"]
    r = client.post(
        "/v1/chat",
        json={"message": "Write a birthday wish for my friend.", "stream": False},
    )
    assert r.status_code == 200
    assert r.json()["answer"] == "I can't know that."
    assert llm.calls == 1


def test_the_model_gets_the_system_prompt_from_the_prompt_file(client):
    assert "not sure" in client.app.state.system_prompt


def test_an_empty_message_is_a_422_problem(client):
    r = client.post("/v1/chat", json={"message": ""})
    assert r.status_code == 422 and r.headers["content-type"] == "application/problem+json"


def test_when_no_model_can_answer_the_api_says_503_not_200(client, llm):
    llm.script = ["docs", LLMError("HTTP 401: invalid API key", retryable=False)]
    r = client.post("/v1/chat", json={"message": "hello"})
    assert r.status_code == 503 and "No model could answer" in r.json()["detail"]


def test_a_failure_in_the_middle_of_a_stream_is_reported_as_an_error_event(client, llm):
    llm.script = ["docs", ("partial", LLMError("HTTP 503: overloaded", retryable=True))]
    r = client.post("/v1/chat", json={"message": "hello"})
    assert r.status_code == 200
    assert events(r.text)[-1][0] == "error"


def test_usage_reports_tokens_and_rupees_per_day(client):
    r = client.get("/v1/usage")
    assert r.status_code == 200
    body = r.json()
    assert body["days"][0]["tokens_in"] == 300 and body["total_cost_inr"] == 0.0642
    assert body["calls"] == 3


def test_prompt_forbids_dates_from_memory(client):
    p = client.app.state.system_prompt
    assert "NEVER state a date or number from memory" in p
