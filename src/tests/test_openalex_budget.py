"""OpenAlex 429 handling: short retries for bursts, immediate stop when the daily budget is gone."""
import pytest
import requests

from src.pathfinding import openalex_client as oc


class FakeResponse:
    def __init__(self, status, headers=None, text="", payload=None):
        self.status_code, self.headers, self.text, self._payload = status, headers or {}, text, payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        return self._payload


def _client(monkeypatch, responses):
    monkeypatch.setattr(oc.time, "sleep", lambda s: None)
    client = oc.OpenAlexClient(use_cache=False)
    queue = list(responses)
    monkeypatch.setattr(client.session, "get", lambda *a, **k: queue.pop(0))
    oc.OpenAlexClient.budget_exhausted = False
    return client


def test_burst_429_is_retried(monkeypatch):
    client = _client(monkeypatch, [
        FakeResponse(429, {"Retry-After": "1"}),
        FakeResponse(200, payload={"results": [1]}),
    ])
    assert client._make_request("/authors") == {"results": [1]}
    assert oc.OpenAlexClient.budget_exhausted is False


def test_exhausted_budget_stops_immediately(monkeypatch):
    client = _client(monkeypatch, [
        FakeResponse(429, {"Retry-After": "48052"}, text='{"error":"Insufficient budget"}'),
    ])
    with pytest.raises(oc.OpenAlexBudgetExceeded):
        client._make_request("/authors")
    assert oc.OpenAlexClient.budget_exhausted is True
    oc.OpenAlexClient.budget_exhausted = False


def test_api_key_is_sent_as_bearer(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "k123")
    assert oc.OpenAlexClient(use_cache=False).session.headers["Authorization"] == "Bearer k123"
