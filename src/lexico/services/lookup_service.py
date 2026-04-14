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
        # v3 prefix invalidates caches that predate the richer Wiktionary parser
        # (examples, derived forms, translations, IPA, POS).
        return f"dict:v3:{language.value}:{lemma.lower()}"

    def _normalize(self, lemma: str) -> str:
        # Wiktionary pages are case-sensitive (fr/paris does not exist, fr/Paris
        # does). We store cache keys lowercased for case-insensitive hits, and
        # try multiple casings at the provider layer. Underscores become spaces
        # (MediaWiki treats them interchangeably in page titles) and repeated
        # whitespace collapses so "from  stem  to  stern" still resolves.
        import re
        cleaned = lemma.replace("_", " ").strip()
        return re.sub(r"\s+", " ", cleaned)

    def _casing_variants(self, lemma: str) -> list[str]:
        seen: list[str] = []
        for v in (lemma, lemma.lower(), lemma.capitalize()):
            if v and v not in seen:
                seen.append(v)
        return seen

    def lookup(self, lemma: str, language: Language) -> WordEntry:
        lemma = self._normalize(lemma)
        if not lemma:
            raise LookupError("Empty lemma")

        key = self._cache_key(lemma, language)

        hit = self._memory.get(key)
        if hit is not None:
            return WordEntry.model_validate(hit)

        raw = self._sqlite.get(key)
        if raw is not None:
            entry = WordEntry.model_validate(raw)
            self._memory.put(key, entry.model_dump(mode="json"))
            return entry

        variants = self._casing_variants(lemma)
        for provider in self._providers:
            for variant in variants:
                try:
                    entry = provider.lookup(variant, language)
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
