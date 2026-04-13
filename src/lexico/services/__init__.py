"""Services package with factory helpers for stores and runtime services."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lexico.services.deck_store import DeckStore
    from lexico.services.enrichment_service import EnrichmentService
    from lexico.services.lookup_service import LookupService


@lru_cache(maxsize=1)
def get_lookup_service() -> "LookupService":
    from lexico.config import settings
    from lexico.providers.base import DictionaryProvider
    from lexico.services.lookup_service import LookupService

    providers: list[DictionaryProvider] = []
    for name in settings.provider_chain:
        if name == "stub":
            from lexico.providers.stub_provider import StubDictionaryProvider
            providers.append(StubDictionaryProvider())
        elif name == "kaikki":
            try:
                from lexico.providers.kaikki_provider import KaikkiProvider

                providers.append(KaikkiProvider(settings.kaikki_dir))
            except Exception:
                pass
    if not providers:
        from lexico.providers.stub_provider import StubDictionaryProvider
        providers.append(StubDictionaryProvider())
    return LookupService(providers, settings.db_path)


@lru_cache(maxsize=1)
def get_enrichment_service() -> "EnrichmentService":
    from lexico.config import settings
    from lexico.providers.base import LlmProvider
    from lexico.services.enrichment_service import EnrichmentService
    from lexico.services.usage_guardrail import UsageGuardrail

    providers: list[LlmProvider] = []
    for name in settings.provider_chain:
        if name == "stub":
            from lexico.providers.stub_provider import StubLlmProvider
            providers.append(StubLlmProvider())
        elif name == "groq" and settings.groq_api_key:
            from lexico.providers.groq_provider import GroqProvider
            providers.append(GroqProvider(settings.groq_api_key, settings.groq_model))
        elif name == "claude" and settings.anthropic_api_key:
            from lexico.providers.claude_provider import ClaudeProvider
            providers.append(ClaudeProvider(settings.anthropic_api_key, settings.claude_lookup_model))
    if not providers:
        from lexico.providers.stub_provider import StubLlmProvider
        providers.append(StubLlmProvider())
    guardrail = UsageGuardrail(
        settings.db_path,
        per_user_daily=settings.max_llm_calls_per_user_per_day,
        global_daily=settings.max_llm_calls_per_day,
        daily_usd_cap=settings.daily_usd_cap,
    )
    return EnrichmentService(providers, guardrail)


@lru_cache(maxsize=1)
def get_deck_store() -> "DeckStore":
    from lexico.config import settings
    from lexico.services.deck_store import DeckStore

    return DeckStore(settings.db_path)
