"""Enumerations used throughout the domain."""

from __future__ import annotations

from enum import Enum


class Language(str, Enum):
    FR = "fr"
    EN = "en"
    IT = "it"
    ES = "es"
    PT = "pt"

    @property
    def display_name(self) -> str:
        return {
            Language.FR: "Français",
            Language.EN: "English",
            Language.IT: "Italiano",
            Language.ES: "Español",
            Language.PT: "Português",
        }[self]

    @property
    def flag(self) -> str:
        return {
            Language.FR: "🇫🇷",
            Language.EN: "🇬🇧",
            Language.IT: "🇮🇹",
            Language.ES: "🇪🇸",
            Language.PT: "🇵🇹",
        }[self]


class PartOfSpeech(str, Enum):
    NOUN = "noun"
    VERB = "verb"
    ADJECTIVE = "adjective"
    ADVERB = "adverb"
    PRONOUN = "pronoun"
    PREPOSITION = "preposition"
    CONJUNCTION = "conjunction"
    INTERJECTION = "interjection"
    DETERMINER = "determiner"
    PHRASE = "phrase"
    OTHER = "other"


class CEFRLevel(str, Enum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class Rating(int, Enum):
    """FSRS rating scale, replaces the old 0-5 stars."""

    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4

    @property
    def label(self) -> str:
        return {
            Rating.AGAIN: "Again",
            Rating.HARD: "Hard",
            Rating.GOOD: "Good",
            Rating.EASY: "Easy",
        }[self]
