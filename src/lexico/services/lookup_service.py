"""LookupService: dictionary provider chain with two-tier caching."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

from lexico.cache.memory_cache import MemoryCache
from lexico.cache.sqlite_cache import SQLiteCache
from lexico.domain.enums import Language
from lexico.domain.word import WordEntry
from lexico.providers.base import DictionaryProvider, LookupError

logger = logging.getLogger(__name__)


class LookupService:
    """Lookup a WordEntry via a provider chain, cached in memory + SQLite.

    Dictionary content is cached indefinitely (no TTL) because lemma
    definitions don't change — there is no reason to re-fetch "chat" in
    French next week.
    """

    def __init__(
        self,
        providers: Sequence[DictionaryProvider],
        db_path: str | Path,
    ) -> None:
        if not providers:
            raise ValueError("LookupService needs at least one DictionaryProvider")
        self._providers = list(providers)
        self._memory = MemoryCache()
        self._sqlite = SQLiteCache(db_path)

    def _cache_key(self, lemma: str, language: Language) -> str:
        # v2 prefix invalidates pre-immersion English-glossed cache entries.
        return f"dict:v2:{language.value}:{lemma.lower()}"

    def lookup(self, lemma: str, language: Language) -> WordEntry:
        key = self._cache_key(lemma, language)

        hit = self._memory.get(key)
        if hit is not None:
            return WordEntry.model_validate(hit)

        raw = self._sqlite.get(key)
        if raw is not None:
            entry = WordEntry.model_validate(raw)
            self._memory.put(key, entry.model_dump(mode="json"))
            return entry

        for provider in self._providers:
            try:
                entry = provider.lookup(lemma, language)
            except LookupError:
                continue
            payload = entry.model_dump(mode="json")
            self._sqlite.put(key, payload)
            self._memory.put(key, payload)
            return entry

        raise LookupError(f"No provider could find {lemma!r} in {language.value}")

    def random_lemma(self, language: Language) -> str | None:
        for provider in self._providers:
            lemma = provider.random_lemma(language) if hasattr(provider, "random_lemma") else None
            if lemma:
                return lemma
        return None

    @property
    def providers(self) -> list[DictionaryProvider]:
        return list(self._providers)
