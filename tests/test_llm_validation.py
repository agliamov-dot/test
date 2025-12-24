from __future__ import annotations

import json
import pytest

from ded_moroz.llm.client import LlmResponse, OpenRouterClient


class DummyResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:  # pragma: no cover
        return

    def json(self) -> dict:
        return self._payload


class DummyClient:
    def __init__(self, payload: dict):
        self.payload = payload

    async def __aenter__(self) -> "DummyClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # pragma: no cover
        return

    async def post(self, *args, **kwargs):  # pragma: no cover
        return DummyResponse(self.payload)


@pytest.mark.asyncio
async def test_llm_valid_json(monkeypatch: pytest.MonkeyPatch, engine) -> None:  # noqa: ARG001
    content = {
        "decision": "ACCEPT",
        "ded_moroz_reply": "Молодец",
        "scores": {"rhyme": 1},
        "reasons": {"tone": "ok"},
        "safety_flag": False,
    }
    payload = {"choices": [{"message": {"content": json.dumps(content)}}]}

    client = OpenRouterClient()
    monkeypatch.setattr("httpx.AsyncClient", lambda: DummyClient(payload))

    response = await client.evaluate_poem("Стих", day=1, user_id=1)
    assert isinstance(response, LlmResponse)
    assert response.decision == "ACCEPT"


@pytest.mark.asyncio
async def test_llm_invalid_json(monkeypatch: pytest.MonkeyPatch, engine) -> None:  # noqa: ARG001
    payload = {"choices": [{"message": {"content": "{bad json}"}}]}
    client = OpenRouterClient()
    monkeypatch.setattr("httpx.AsyncClient", lambda: DummyClient(payload))

    with pytest.raises(ValueError):
        await client.evaluate_poem("Стих", day=1, user_id=1)
