"""WiktionaryProvider tests — mocked fetch, no network."""

from __future__ import annotations

import pytest

from lexico.domain.enums import Language, PartOfSpeech
from lexico.providers.base import LookupError
from lexico.providers.wiktionary_provider import WiktionaryProvider


@pytest.fixture
def provider() -> WiktionaryProvider:
    return WiktionaryProvider()


def test_parses_definition_with_html(provider, monkeypatch):
    payload = {
        "en": [
            {
                "partOfSpeech": "Noun",
                "language": "English",
                "definitions": [
                    {
                        "definition": "A small <a href='/wiki/domesticated'>domesticated</a> carnivorous mammal.",
                        "examples": ["The <b>cat</b> is on the mat."],
                    }
                ],
            }
        ]
    }
    monkeypatch.setattr(provider, "_fetch", lambda lemma: payload)

    entry = provider.lookup("cat", Language.EN)

    assert entry.lemma == "cat"
    assert entry.language == Language.EN
    assert entry.source == "wiktionary"
    assert len(entry.senses) == 1
    sense = entry.senses[0]
    assert sense.part_of_speech == PartOfSpeech.NOUN
    assert "domesticated carnivorous mammal" in sense.gloss
    assert "<a" not in sense.gloss
    assert len(sense.examples) == 1
    assert "cat" in sense.examples[0].text
    assert "<b>" not in sense.examples[0].text


def test_filters_to_requested_language(provider, monkeypatch):
    payload = {
        "en": [
            {
                "partOfSpeech": "Noun",
                "language": "English",
                "definitions": [{"definition": "A chat (English sense)."}],
            }
        ],
        "fr": [
            {
                "partOfSpeech": "Noun",
                "language": "French",
                "definitions": [{"definition": "Un petit animal domestique."}],
            }
        ],
    }
    monkeypatch.setattr(provider, "_fetch", lambda lemma: payload)

    fr_entry = provider.lookup("chat", Language.FR)
    assert fr_entry.language == Language.FR
    assert "domestique" in fr_entry.senses[0].gloss

    en_entry = provider.lookup("chat", Language.EN)
    assert en_entry.language == Language.EN
    assert "English sense" in en_entry.senses[0].gloss


def test_missing_language_section_raises(provider, monkeypatch):
    monkeypatch.setattr(
        provider,
        "_fetch",
        lambda lemma: {"en": [{"partOfSpeech": "Noun", "definitions": [{"definition": "x"}]}]},
    )
    with pytest.raises(LookupError):
        provider.lookup("whatever", Language.FR)


def test_empty_fetch_raises(provider, monkeypatch):
    monkeypatch.setattr(provider, "_fetch", lambda lemma: None)
    with pytest.raises(LookupError):
        provider.lookup("chat", Language.FR)


def test_all_empty_definitions_raises(provider, monkeypatch):
    payload = {
        "fr": [
            {"partOfSpeech": "Noun", "definitions": [{"definition": ""}, {"definition": None}]}
        ]
    }
    monkeypatch.setattr(provider, "_fetch", lambda lemma: payload)
    with pytest.raises(LookupError):
        provider.lookup("chat", Language.FR)


def test_parses_parsed_examples(provider, monkeypatch):
    payload = {
        "fr": [
            {
                "partOfSpeech": "Noun",
                "definitions": [
                    {
                        "definition": "Un mammifère.",
                        "parsedExamples": [{"example": "Le <i>chat</i> dort."}],
                    }
                ],
            }
        ]
    }
    monkeypatch.setattr(provider, "_fetch", lambda lemma: payload)
    entry = provider.lookup("chat", Language.FR)
    assert len(entry.senses[0].examples) == 1
    assert entry.senses[0].examples[0].text == "Le chat dort."
