import os
from types import SimpleNamespace

import pytest


os.environ.setdefault("AGENT_URL", "https://agent.example.com")

from zoo_chat_ui import app as chat_app
from zoo_chat_ui.app import execution_trace


class FakeCache:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self.values[key] = value


class UnavailableCache:
    def get(self, key):
        raise RuntimeError("Redis is unavailable")

    def setex(self, key, ttl, value):
        raise RuntimeError("Redis is unavailable")


@pytest.fixture
def client(monkeypatch):
    cache = FakeCache()
    monkeypatch.setattr(chat_app, "get_cache_client", lambda: cache)
    monkeypatch.setattr(chat_app, "is_rate_limited", lambda: False)
    monkeypatch.setattr(
        chat_app.auth,
        "verify_id_token",
        lambda token: {"uid": token, "email": f"{token}@example.com"},
    )
    monkeypatch.setattr(chat_app, "firebase_enabled", True)
    monkeypatch.setattr(chat_app, "agent_headers", lambda: {})
    monkeypatch.setattr(chat_app, "request_timestamps", {})
    return chat_app.app.test_client(), cache


def test_execution_trace_includes_agent_transfers_and_tool_names_only():
    events = [
        {
            "content": {
                "parts": [
                    {
                        "functionCall": {
                            "name": "transfer_to_agent",
                            "args": {"agent_name": "travel_planner_agent"},
                        }
                    }
                ]
            },
            "actions": {"transferToAgent": "travel_planner_agent"},
        },
        {
            "content": {
                "parts": [
                    {
                        "functionCall": {
                            "name": "get_weather_forecast",
                            "args": {"zoo_id": "chicago", "visit_date": "2026-09-03"},
                        }
                    }
                ]
            }
        },
    ]

    assert execution_trace(events) == [
        {"type": "agent", "name": "travel_planner_agent"},
        {"type": "tool", "name": "get_weather_forecast"},
    ]


def test_exact_repeat_uses_cached_answer_for_same_user_and_session(client, monkeypatch):
    test_client, cache = client
    calls = []

    def post(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: [
                {"content": {"parts": [{"text": "Asha is an Asian elephant."}]}}
            ],
        )

    monkeypatch.setattr(chat_app.requests, "post", post)
    headers = {"Authorization": "Bearer visitor"}
    payload = {"sessionId": "session-one", "message": "Tell me about Asha."}

    first = test_client.post("/api/chat", headers=headers, json=payload)
    second = test_client.post(
        "/api/chat",
        headers=headers,
        json={**payload, "message": "  TELL me about asha.  "},
    )

    assert first.get_json()["cached"] is False
    assert second.get_json() == {
        "answer": "Asha is an Asian elephant.",
        "cached": True,
        "execution": [],
    }
    assert len(calls) == 1
    assert all("visitor" not in value for value in cache.values.values())


def test_answer_cache_isolated_by_user_and_session(client, monkeypatch):
    test_client, _ = client
    calls = []

    def post(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: [{"content": {"parts": [{"text": "Answer"}]}}],
        )

    monkeypatch.setattr(chat_app.requests, "post", post)
    message = "Tell me about elephants."
    test_client.post(
        "/api/chat",
        headers={"Authorization": "Bearer one"},
        json={"sessionId": "a", "message": message},
    )
    test_client.post(
        "/api/chat",
        headers={"Authorization": "Bearer one"},
        json={"sessionId": "b", "message": message},
    )
    test_client.post(
        "/api/chat",
        headers={"Authorization": "Bearer two"},
        json={"sessionId": "a", "message": message},
    )

    assert len(calls) == 3


def test_dynamic_messages_are_not_answer_cached(client, monkeypatch):
    test_client, _ = client
    calls = []

    def post(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: [{"content": {"parts": [{"text": "Weather answer"}]}}],
        )

    monkeypatch.setattr(chat_app.requests, "post", post)
    headers = {"Authorization": "Bearer visitor"}
    payload = {"sessionId": "a", "message": "What is the weather today?"}

    test_client.post("/api/chat", headers=headers, json=payload)
    test_client.post("/api/chat", headers=headers, json=payload)

    assert len(calls) == 2


def test_cache_failures_fall_through_to_the_agent(client, monkeypatch):
    test_client, _ = client
    monkeypatch.setattr(chat_app, "get_cache_client", lambda: UnavailableCache())
    monkeypatch.setattr(
        chat_app.requests,
        "post",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: [{"content": {"parts": [{"text": "Agent answer"}]}}],
        ),
    )

    response = test_client.post(
        "/api/chat",
        headers={"Authorization": "Bearer visitor"},
        json={"sessionId": "a", "message": "Tell me about elephants."},
    )

    assert response.get_json()["answer"] == "Agent answer"
    assert response.get_json()["cached"] is False