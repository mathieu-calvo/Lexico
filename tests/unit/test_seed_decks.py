"""Seed-deck loader and cloning tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lexico.domain.enums import Language
from lexico.providers.stub_provider import StubDictionaryProvider
from lexico.services.deck_store import DeckStore
from lexico.services.lookup_service import LookupService
from lexico.services.seed_decks import (
    SeedDeck,
    clone_seed_deck,
    list_seed_decks,
)


def test_bundled_seed_decks_load():
    """The shipped YAML files should all parse."""
    decks = list_seed_decks()
    assert len(decks) >= 3
    slugs = {d.slug for d in decks}
    assert "cafe_fr" in slugs
    for deck in decks:
        assert deck.name
        assert isinstance(deck.source_lang, Language)
        assert isinstance(deck.target_lang, Language)
        assert len(deck.lemmas) > 0


def test_custom_seed_deck_roundtrip(tmp_path: Path):
    yaml_text = yaml.safe_dump(
        {
            "name": "Tiny FR",
            "source_lang": "fr",
            "target_lang": "en",
            "description": "Tiny test deck",
            "lemmas": ["chat", "bonjour", "nonexistent"],
        }
    )
    (tmp_path / "tiny_fr.yaml").write_text(yaml_text, encoding="utf-8")

    decks = list_seed_decks(tmp_path)
    assert len(decks) == 1
    seed = decks[0]
    assert seed.slug == "tiny_fr"
    assert seed.source_lang == Language.FR
    assert seed.target_lang == Language.EN
    assert seed.lemmas == ("chat", "bonjour", "nonexistent")


def test_malformed_yaml_is_skipped(tmp_path: Path):
    (tmp_path / "good.yaml").write_text(
        yaml.safe_dump(
            {"name": "Good", "source_lang": "fr", "target_lang": "en", "lemmas": ["chat"]}
        ),
        encoding="utf-8",
    )
    (tmp_path / "bad.yaml").write_text("::: not valid yaml :::", encoding="utf-8")

    decks = list_seed_decks(tmp_path)
    assert [d.slug for d in decks] == ["good"]


def test_clone_hydrates_via_lookup(tmp_path: Path):
    seed = SeedDeck(
        slug="stub_fr",
        name="Stub FR",
        source_lang=Language.FR,
        target_lang=Language.EN,
        description="",
        lemmas=("chat", "bonjour", "nonexistent_word"),
    )
    store = DeckStore(tmp_path / "lexico.db")
    lookup = LookupService([StubDictionaryProvider()], tmp_path / "lexico.db")

    deck, added, skipped = clone_seed_deck(seed, store, lookup, user_id="tester")

    assert deck.id is not None
    assert added == 2
    assert skipped == 1
    cards = store.list_cards(deck.id)
    lemmas = {c.entry.lemma for c in cards}
    assert lemmas == {"chat", "bonjour"}
