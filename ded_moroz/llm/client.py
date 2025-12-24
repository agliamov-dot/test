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


PROMPT_SYSTEM = (
    "Ты — строгий, но добрый Дед Мороз, проверяющий новогодние стихи. "
    "Отвечай саркастично, но без оскорблений. Возвращай JSON согласно схеме."
)


class OpenRouterClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.openrouter.api_key
        self.base_url = base_url or settings.openrouter.base_url
        self.model = model or settings.openrouter.model

    async def evaluate_poem(self, poem: str, day: int, user_id: int) -> LlmResponse:
        schema = {
            "name": "PoemDecision",
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
            "strict": True,
        }
        payload = {
            "model": self.model,
            "response_format": {"type": "json_schema", "json_schema": schema},
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
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if not content:
            raise ValueError("Empty response from LLM")
        try:
            parsed = json.loads(content)
            return LlmResponse.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError("LLM response validation failed") from exc
