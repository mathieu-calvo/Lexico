"""DeckStore tests against a temporary SQLite file."""

from __future__ import annotations

from datetime import timedelta

import pytest

from lexico.domain.deck import Card, Deck
from lexico.domain.enums import Language, Rating
from lexico.services.deck_store import DeckStore
from lexico.services.review_scheduler import schedule


@pytest.fixture
def store(tmp_path):
    return DeckStore(tmp_path / "lexico.db")


def test_create_deck_assigns_id(store):
    deck = store.create_deck(
        Deck(name="French Basics", source_lang=Language.FR, target_lang=Language.EN)
    )
    assert deck.id is not None


def test_list_decks_returns_created(store):
    store.create_deck(Deck(name="A", source_lang=Language.FR, target_lang=Language.EN))
    store.create_deck(Deck(name="B", source_lang=Language.IT, target_lang=Language.EN))
    decks = store.list_decks()
    names = {d.name for d in decks}
    assert names == {"A", "B"}


def test_delete_deck_cascades_cards(store, stub_dict):
    deck = store.create_deck(
        Deck(name="X", source_lang=Language.FR, target_lang=Language.EN)
    )
    card = Card.new(entry=stub_dict.lookup("chat", Language.FR), deck_id=deck.id)
    store.add_card(card)
    store.delete_deck(deck.id)
    assert store.list_decks() == []
    assert store.count_cards() == 0


def test_add_card_and_list(store, stub_dict):
    deck = store.create_deck(
        Deck(name="Y", source_lang=Language.FR, target_lang=Language.EN)
    )
    card = Card.new(entry=stub_dict.lookup("chat", Language.FR), deck_id=deck.id)
    saved = store.add_card(card)
    assert saved.id is not None
    cards = store.list_cards(deck.id)
    assert len(cards) == 1
    assert cards[0].entry.lemma == "chat"


def test_due_cards_respect_schedule(store, stub_dict, now):
    deck = store.create_deck(
        Deck(name="Z", source_lang=Language.FR, target_lang=Language.EN)
    )
    card = Card.new(entry=stub_dict.lookup("chat", Language.FR), deck_id=deck.id)
    saved = store.add_card(card)

    new_state, _ = schedule(saved.fsrs_state, Rating.GOOD, now)
    store.update_card_state(saved.id, new_state)

    assert store.get_due_cards(now=now - timedelta(days=1)) == []
    due_after = store.get_due_cards(now=new_state.due_at + timedelta(days=1))
    assert len(due_after) == 1


def test_log_review_and_list(store, stub_dict, now):
    deck = store.create_deck(
        Deck(name="R", source_lang=Language.FR, target_lang=Language.EN)
    )
    card = Card.new(entry=stub_dict.lookup("chat", Language.FR), deck_id=deck.id)
    saved = store.add_card(card)
    _, log = schedule(saved.fsrs_state, Rating.GOOD, now)
    log = log.model_copy(update={"card_id": saved.id})
    store.log_review(log, user_id="local", language=Language.FR)
    logs = store.list_review_logs()
    assert len(logs) == 1
    assert logs[0]["rating"] == int(Rating.GOOD)


def test_llm_usage_counts(store):
    store.log_llm_usage("local", "stub", "stub-1", 10, 20, 0.0)
    store.log_llm_usage("local", "groq", "llama", 30, 50, 0.0)
    assert store.llm_calls_today("local") == 2
    assert store.llm_usd_today() == 0.0
