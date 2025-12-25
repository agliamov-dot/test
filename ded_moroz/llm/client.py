from __future__ import annotations

import json
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ValidationError

from ded_moroz.config import settings
from ded_moroz.db.models import SafetyStatus

DecisionLiteral = Literal["ACCEPT", "RETRY", "REJECT"]


class LlmResponse(BaseModel):
    decision: DecisionLiteral
    ded_moroz_reply: str
    scores: dict[str, Any] | None = None
    reasons: dict[str, Any] | None = None
    safety_flag: bool = False
    safety_status: SafetyStatus = SafetyStatus.SAFE


class LlmClientError(Exception):
    """Raised when the LLM client fails to return a valid response."""


PROMPT_SYSTEM = (
    "Ты — строгий, но добрый Дед Мороз, проверяющий новогодние стихи. "
    "Отвечай саркастично, но без оскорблений. Возвращай JSON согласно схеме."
)


LLM_JSON_SCHEMA = {
    "name": "PoemDecision",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["ACCEPT", "RETRY", "REJECT"]},
            "ded_moroz_reply": {"type": "string"},
            "scores": {"type": "object"},
            "reasons": {"type": "object"},
            "safety_flag": {"type": "boolean"},
            "safety_status": {"type": "string", "enum": [item.value for item in SafetyStatus]},
        },
        "required": ["decision", "ded_moroz_reply"],
        "additionalProperties": False,
    },
}


def _extract_payload(data: dict[str, Any]) -> dict[str, Any]:
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:  # pragma: no cover - defensive
        raise LlmClientError("Malformed LLM response: missing message") from exc

    if not message:
        raise LlmClientError("Malformed LLM response: empty message")

    if isinstance(message, dict) and message.get("parsed"):
        parsed = message["parsed"]
        if not isinstance(parsed, dict):
            raise LlmClientError("Malformed LLM response: `parsed` must be an object")
        return parsed

    content = message.get("content") if isinstance(message, dict) else None

    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict)).strip() or None

    if isinstance(content, dict):
        payload = content
    elif isinstance(content, str):
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:  # pragma: no cover - parsing guard
            raise LlmClientError("Malformed LLM response: invalid JSON content") from exc
    else:
        raise LlmClientError("Malformed LLM response: empty content")

    if not isinstance(payload, dict):
        raise LlmClientError("Malformed LLM response: payload must be an object")
    return payload


class OpenRouterClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.openrouter.api_key
        self.base_url = base_url or settings.openrouter.base_url
        self.model = model or settings.openrouter.model

    async def evaluate_poem(self, poem: str, day: int, user_id: int) -> LlmResponse:
        payload = {
            "model": self.model,
            "response_format": {"type": "json_schema", "json_schema": LLM_JSON_SCHEMA},
            "messages": [
                {"role": "system", "content": PROMPT_SYSTEM},
                {
                    "role": "user",
                    "content": f"День: {day}. Пользователь: {user_id}. Стих: {poem}",
                },
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://openrouter.ai/",
            "X-Title": "Ded Moroz Advent Bot",
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=60
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - network errors
            raise LlmClientError("LLM request failed with HTTP error") from exc
        except httpx.RequestError as exc:  # pragma: no cover - network errors
            raise LlmClientError("LLM request failed") from exc

        try:
            parsed_payload = _extract_payload(data)
            return LlmResponse.model_validate(parsed_payload)
        except (ValidationError, LlmClientError) as exc:
            raise LlmClientError("LLM response validation failed") from exc
