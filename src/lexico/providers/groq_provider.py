"""Groq free-tier LLM provider (Llama 3.3 70B)."""

from __future__ import annotations

import logging

from lexico.providers.base import LlmResponse, LlmUsage

logger = logging.getLogger(__name__)


class GroqProvider:
    """Wraps the groq SDK for Llama 3.3 70B chat completions.

    Free tier cost is $0/call, so `usage.usd` is always 0. Token counts
    are reported back so the caller can log them for observability.
    """

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile") -> None:
        self._api_key = api_key
        self._model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from groq import Groq
            self._client = Groq(api_key=self._api_key)
        return self._client

    @property
    def name(self) -> str:
        return "groq"

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 512,
        json_mode: bool = False,
    ) -> LlmResponse:
        client = self._get_client()
        kwargs: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.6,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)
        text = response.choices[0].message.content or ""
        usage = response.usage
        return LlmResponse(
            text=text,
            usage=LlmUsage(
                provider="groq",
                model=self._model,
                tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
                tokens_out=getattr(usage, "completion_tokens", 0) or 0,
                usd=0.0,
            ),
        )
