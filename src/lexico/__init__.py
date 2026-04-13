"""Lexico: multilingual dictionary and spaced-repetition vocabulary companion."""

from lexico.domain.enums import Language, PartOfSpeech, Rating
from lexico.domain.deck import Card, Deck
from lexico.domain.review import FSRSState, ReviewLog
from lexico.domain.word import Example, Sense, WordEntry

__all__ = [
    "Card",
    "Deck",
    "Example",
    "FSRSState",
    "Language",
    "PartOfSpeech",
    "Rating",
    "ReviewLog",
    "Sense",
    "WordEntry",
]
