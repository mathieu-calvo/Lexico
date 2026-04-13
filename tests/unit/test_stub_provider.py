"""Stub provider tests."""

from __future__ import annotations

import pytest

from lexico.domain.enums import Language
from lexico.providers.base import LookupError
from lexico.providers.stub_provider import StubDictionaryProvider


def test_stub_dict_lookup_returns_entry():
    provider = StubDictionaryProvider()
    entry = provider.lookup("chat", Language.FR)
    assert entry.lemma == "chat"
    assert entry.language == Language.FR
    assert entry.primary_translation(Language.EN) == "cat"


def test_stub_dict_lookup_is_case_insensitive():
    provider = StubDictionaryProvider()
    assert provider.lookup("CHAT", Language.FR).lemma == "chat"


def test_stub_dict_lookup_raises_for_unknown():
    provider = StubDictionaryProvider()
    with pytest.raises(LookupError):
        provider.lookup("xyzzy", Language.FR)


@pytest.mark.parametrize("language", list(Language))
def test_stub_dict_has_at_least_5_entries_per_language(language):
    provider = StubDictionaryProvider()
    lemmas = provider.all_lemmas(language)
    assert len(lemmas) >= 5


@pytest.mark.parametrize("language", list(Language))
def test_stub_dict_random_lemma_is_deterministic_per_day(language):
    provider = StubDictionaryProvider()
    a = provider.random_lemma(language)
    b = provider.random_lemma(language)
    assert a == b
    assert a is not None


def test_stub_llm_is_available(stub_llm):
    assert stub_llm.is_available is True


def test_stub_llm_complete_is_deterministic(stub_llm):
    r1 = stub_llm.complete("sys", "hello")
    r2 = stub_llm.complete("sys", "hello")
    assert r1.text == r2.text
    assert r1.usage.usd == 0.0


def test_stub_llm_json_mode_returns_parseable(stub_llm):
    import json

    r = stub_llm.complete("sys", "make a cloze", json_mode=True)
    data = json.loads(r.text)
    assert "sentence" in data
    assert "distractors" in data
