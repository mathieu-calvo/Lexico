"""Unit tests for WiktionaryNativeProvider.

All fetches are monkey-patched — no network, no keys.
"""

from __future__ import annotations

import pytest

from lexico.domain.enums import Language
from lexico.providers.base import LookupError
from lexico.providers.wiktionary_native_provider import (
    WiktionaryNativeProvider,
    _clean_wikitext,
    _extract_etymology,
    _extract_glosses,
    _find_section,
)


FR_CHAT_WIKITEXT = """== {{langue|fr}} ==
=== {{S|étymologie}} ===
: Du latin {{lang|la|cattus}}, « chat domestique ».

=== {{S|nom|fr}} ===
# [[mammifère|Mammifère]] carnivore de la famille des [[félidés]], couramment élevé comme animal de compagnie.
#* ''Le chat dort sur le canapé.''
# {{familier|fr}} Personne rusée.
"""

IT_GATTO_WIKITEXT = """== {{-it-}} ==
=== {{-etim-}} ===
Dal latino ''cattus''.

=== {{-noun-}} ===
# piccolo [[mammifero]] carnivoro domestico della famiglia dei [[felidi]]
#: ''Il gatto dorme sul divano.''
# persona furba
"""

ES_HOLA_WIKITEXT = """== {{lengua|es}} ==
=== Etimología ===
Origen incierto, atestiguado desde el español medieval.

=== {{interjección}} ===
# [[saludo|Saludo]] informal usado al encontrarse con alguien.
"""


def test_clean_wikitext_strips_templates_and_links():
    raw = "Du {{lang|la|cattus}}, « [[chat|chat]] [[domestique]] »."
    assert _clean_wikitext(raw) == "Du , « chat domestique »."


def test_clean_wikitext_handles_bold_italic_and_refs():
    raw = "'''Bold''' and ''italic'' with <ref>source</ref> trailing."
    assert _clean_wikitext(raw) == "Bold and italic with trailing."


def test_extract_glosses_skips_examples_and_sublines():
    glosses = _extract_glosses(FR_CHAT_WIKITEXT)
    assert len(glosses) == 2
    assert "Mammifère carnivore" in glosses[0]
    assert "Personne rusée" in glosses[1]


def test_extract_glosses_italian():
    glosses = _extract_glosses(IT_GATTO_WIKITEXT)
    assert any("mammifero" in g.lower() for g in glosses)
    assert not any("dorme sul" in g for g in glosses)  # example is skipped


def test_extract_etymology_french():
    ety = _extract_etymology(FR_CHAT_WIKITEXT, ("Étymologie",))
    assert ety is not None
    assert "latin" in ety.lower()


def test_extract_etymology_spanish():
    ety = _extract_etymology(ES_HOLA_WIKITEXT, ("Etimología",))
    assert ety is not None
    assert "medieval" in ety.lower()


def test_find_section_matches_native_header():
    sections = [
        {"line": "Anglais", "number": "1"},
        {"line": "Français", "number": "2"},
    ]
    assert _find_section(sections, "Français") == "2"
    assert _find_section(sections, "Italiano") is None


def test_lookup_end_to_end_mocked(monkeypatch):
    provider = WiktionaryNativeProvider()

    def fake_sections(self, lemma, language):
        assert language == Language.FR
        return [{"line": "Français", "number": "3"}]

    def fake_wikitext(self, lemma, language, section):
        assert section == "3"
        return FR_CHAT_WIKITEXT

    monkeypatch.setattr(
        WiktionaryNativeProvider, "_fetch_sections", fake_sections
    )
    monkeypatch.setattr(
        WiktionaryNativeProvider, "_fetch_wikitext", fake_wikitext
    )

    entry = provider.lookup("chat", Language.FR)
    assert entry.lemma == "chat"
    assert entry.language == Language.FR
    assert entry.source == "wiktionary-native"
    assert len(entry.senses) >= 1
    assert "Mammifère" in entry.senses[0].gloss
    assert entry.etymology is not None
    assert "latin" in entry.etymology.lower()


def test_lookup_raises_when_no_sections(monkeypatch):
    provider = WiktionaryNativeProvider()
    monkeypatch.setattr(
        WiktionaryNativeProvider,
        "_fetch_sections",
        lambda self, lemma, language: None,
    )
    with pytest.raises(LookupError):
        provider.lookup("nope", Language.FR)


def test_lookup_raises_when_native_section_missing(monkeypatch):
    provider = WiktionaryNativeProvider()
    monkeypatch.setattr(
        WiktionaryNativeProvider,
        "_fetch_sections",
        lambda self, lemma, language: [{"line": "Anglais", "number": "1"}],
    )
    with pytest.raises(LookupError, match="section"):
        provider.lookup("chat", Language.FR)


def test_lookup_raises_when_no_glosses(monkeypatch):
    provider = WiktionaryNativeProvider()
    monkeypatch.setattr(
        WiktionaryNativeProvider,
        "_fetch_sections",
        lambda self, lemma, language: [{"line": "Français", "number": "1"}],
    )
    monkeypatch.setattr(
        WiktionaryNativeProvider,
        "_fetch_wikitext",
        lambda self, lemma, language, section: "== header ==\nno definitions here\n",
    )
    with pytest.raises(LookupError, match="definitions"):
        provider.lookup("chat", Language.FR)
