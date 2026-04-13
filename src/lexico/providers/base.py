"""Provider protocols for dictionary lookup and LLM enrichment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from lexico.domain.enums import Language
from lexico.domain.word import WordEntry


class LookupError(Exception):
    """Raised when a provider cannot find an entry."""


@runtime_checkable
class DictionaryProvider(Protocol):
    """Protocol for anything that returns a WordEntry for a (lemma, language)."""

    @property
    def name(self) -> str: ...

    def lookup(self, lemma: str, language: Language) -> WordEntry: ...

    def random_lemma(self, language: Language) -> str | None:
        """Return a random lemma for word-of-the-day rotation. Optional."""
        ...


@dataclass(frozen=True)
class LlmUsage:
    """Token and cost accounting returned by an LlmProvider call."""

    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    usd: float


@dataclass(frozen=True)
class LlmResponse:
    """Wrapper for LLM output + usage metadata."""

    text: str
    usage: LlmUsage


@runtime_checkable
class LlmProvider(Protocol):
    """Protocol for LLM-backed enrichment calls."""

    @property
    def name(self) -> str: ...

    @property
    def is_available(self) -> bool:
        """True when the provider has credentials and can make calls."""
        ...

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 512,
        json_mode: bool = False,
    ) -> LlmResponse: ...
