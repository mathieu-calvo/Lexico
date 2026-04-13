"""Optional Claude LLM provider (paid, capped by UsageGuardrail)."""

from __future__ import annotations

import logging

from lexico.providers.base import LlmResponse, LlmUsage

logger = logging.getLogger(__name__)

# Rough per-1M-token prices for claude-haiku-4-5 (adjust as needed).
_HAIKU_INPUT_PER_MTOK = 1.00
_HAIKU_OUTPUT_PER_MTOK = 5.00


class ClaudeProvider:
    """Wraps the anthropic SDK. Uses prompt caching for the system prompt."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5") -> None:
        self._api_key = api_key
        self._model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self._api_key)
        return self._client

    @property
    def name(self) -> str:
        return "claude"

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
        sys_block = [
            {
                "type": "text",
                "text": system + ("\n\nRespond with strict JSON only." if json_mode else ""),
                "cache_control": {"type": "ephemeral"},
            }
        ]
        response = client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=sys_block,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        usage = response.usage
        tokens_in = getattr(usage, "input_tokens", 0) or 0
        tokens_out = getattr(usage, "output_tokens", 0) or 0
        usd = (tokens_in / 1_000_000) * _HAIKU_INPUT_PER_MTOK + (
            tokens_out / 1_000_000
        ) * _HAIKU_OUTPUT_PER_MTOK
        return LlmResponse(
            text=text,
            usage=LlmUsage(
                provider="claude",
                model=self._model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                usd=usd,
            ),
        )
