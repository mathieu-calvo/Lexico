"""Shared fixtures for unit tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from lexico.domain.deck import Card, Deck
from lexico.domain.enums import Language
from lexico.providers.stub_provider import StubDictionaryProvider, StubLlmProvider


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 4, 13, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def stub_dict() -> StubDictionaryProvider:
    return StubDictionaryProvider()


@pytest.fixture
def stub_llm() -> StubLlmProvider:
    return StubLlmProvider()


@pytest.fixture
def sample_deck() -> Deck:
    return Deck(
        id=1,
        user_id="local",
        name="Test French",
        source_lang=Language.FR,
        target_lang=Language.EN,
    )


@pytest.fixture
def sample_card(stub_dict: StubDictionaryProvider) -> Card:
    entry = stub_dict.lookup("chat", Language.FR)
    return Card.new(entry=entry, deck_id=1)
