"""Domain model tests."""

from __future__ import annotations

import pytest

from lexico.domain.enums import Language, PartOfSpeech, Rating
from lexico.domain.review import FSRSState
from lexico.domain.word import Example, Sense, WordEntry


def test_word_entry_cache_key_normalizes_lemma():
    entry = WordEntry(lemma="Chat", language=Language.FR)
    assert entry.cache_key == "fr:chat:stub"


def test_word_entry_is_frozen():
    entry = WordEntry(lemma="chat", language=Language.FR)
    with pytest.raises(Exception):
        entry.lemma = "dog"  # type: ignore[misc]


def test_word_entry_primary_translation():
    entry = WordEntry(
        lemma="chat",
        language=Language.FR,
        translations={Language.EN: ("cat", "feline")},
    )
    assert entry.primary_translation(Language.EN) == "cat"
    assert entry.primary_translation(Language.IT) is None


def test_sense_holds_examples_and_synonyms():
    sense = Sense(
        gloss="cat",
        part_of_speech=PartOfSpeech.NOUN,
        examples=(Example(text="Le chat dort.", translation="The cat sleeps."),),
        synonyms=("minet",),
    )
    assert sense.examples[0].text == "Le chat dort."
    assert sense.synonyms == ("minet",)


def test_rating_labels():
    assert Rating.GOOD.label == "Good"
    assert Rating.AGAIN.label == "Again"


def test_fsrs_state_new_is_new(now):
    state = FSRSState.new(now)
    assert state.is_new is True
    assert state.reps == 0
    assert state.due_at == now


def test_language_has_display_and_flag():
    assert Language.FR.display_name == "Français"
    assert Language.FR.flag == "🇫🇷"
