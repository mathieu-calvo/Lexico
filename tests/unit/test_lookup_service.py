"""LookupService tests, backed by StubDictionaryProvider and in-memory SQLite."""

from __future__ import annotations

import pytest

from lexico.domain.enums import Language
from lexico.providers.base import LookupError
from lexico.providers.stub_provider import StubDictionaryProvider
from lexico.services.lookup_service import LookupService


@pytest.fixture
def service(tmp_path):
    db = tmp_path / "lexico.db"
    return LookupService([StubDictionaryProvider()], db)


def test_lookup_returns_entry(service):
    entry = service.lookup("chat", Language.FR)
    assert entry.lemma == "chat"
    assert entry.language == Language.FR


def test_lookup_uses_cache_on_second_call(service):
    service.lookup("chat", Language.FR)
    entry = service.lookup("chat", Language.FR)
    assert entry.lemma == "chat"


def test_lookup_survives_memory_clear_via_sqlite(tmp_path):
    db = tmp_path / "lexico.db"
    svc1 = LookupService([StubDictionaryProvider()], db)
    svc1.lookup("chat", Language.FR)
    svc2 = LookupService([StubDictionaryProvider()], db)
    entry = svc2.lookup("chat", Language.FR)
    assert entry.lemma == "chat"


def test_lookup_unknown_raises(service):
    with pytest.raises(LookupError):
        service.lookup("xyzzy", Language.FR)


def test_lookup_requires_at_least_one_provider(tmp_path):
    with pytest.raises(ValueError):
        LookupService([], tmp_path / "db.sqlite")


def test_lookup_falls_through_to_second_provider(tmp_path):
    class Empty:
        name = "empty"
        def lookup(self, lemma, language):
            raise LookupError("empty")
        def random_lemma(self, language):
            return None

    svc = LookupService([Empty(), StubDictionaryProvider()], tmp_path / "db.sqlite")
    assert svc.lookup("chat", Language.FR).lemma == "chat"


def test_random_lemma_returns_known_word(service):
    lemma = service.random_lemma(Language.FR)
    assert lemma is not None


def test_lookup_normalizes_whitespace(service):
    entry = service.lookup("  chat  ", Language.FR)
    assert entry.lemma == "chat"


def test_lookup_tries_case_variants(tmp_path):
    """Provider sees case variants in order until one succeeds.

    Simulates a provider that only has the lowercased form (how Wiktionary
    would react for a common noun typed in sentence case).
    """
    seen: list[str] = []

    class CaseSensitive:
        name = "case"
        def lookup(self, lemma, language):
            seen.append(lemma)
            if lemma != "chat":
                raise LookupError(f"no {lemma}")
            return StubDictionaryProvider().lookup("chat", language)
        def random_lemma(self, language):
            return None

    svc = LookupService([CaseSensitive()], tmp_path / "db.sqlite")
    entry = svc.lookup("Chat", Language.FR)
    assert entry.lemma == "chat"
    # Variants tried in order: original, lowercase — the capitalize variant
    # collapses with the original so it's deduped out.
    assert seen == ["Chat", "chat"]


def test_lookup_empty_string_raises(service):
    with pytest.raises(LookupError):
        service.lookup("   ", Language.FR)


def test_lookup_normalizes_underscores_and_whitespace(tmp_path):
    """Accept `from_stem_to_stern` and `from  stem  to  stern` for multi-word lemmas."""
    from lexico.domain.word import Sense, WordEntry

    captured: list[str] = []

    class RecordingProvider:
        name = "record"
        def lookup(self, lemma, language):
            captured.append(lemma)
            if lemma != "from stem to stern":
                raise LookupError(f"no {lemma}")
            return WordEntry(
                lemma=lemma,
                language=language,
                senses=(Sense(gloss="Over the full length of a ship."),),
            )
        def random_lemma(self, language):
            return None

    svc = LookupService([RecordingProvider()], tmp_path / "db.sqlite")
    svc.lookup("from_stem_to_stern", Language.EN)
    # Second call hits the cache (same normalized key) so doesn't reach the
    # provider again — captured stays at 1 hit from the first call.
    svc.lookup("  from  stem   to  stern  ", Language.EN)
    assert "from stem to stern" in captured
