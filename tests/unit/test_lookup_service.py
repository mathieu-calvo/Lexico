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
