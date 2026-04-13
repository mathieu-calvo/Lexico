"""Unit tests for WiktionaryNativeProvider.

All fetches are monkey-patched — no network, no keys.
"""

from __future__ import annotations

import pytest

from lexico.domain.enums import Language
from lexico.providers.base import LookupError
from lexico.providers.wiktionary_native_provider import (
    WiktionaryNativeProvider,
    _extract_etymology_from_html,
    _extract_glosses,
    _find_section_index,
    _strip_tags,
)


FR_CHAT_HTML = """
<h3><span class="mw-headline">Étymologie</span></h3>
<p>Du latin <i>cattus</i>, emprunt probable à une langue africaine.</p>
<h3><span class="mw-headline">Nom commun</span></h3>
<ol>
  <li>Mammifère carnivore félin de taille moyenne, au museau court, domestiqué comme animal de compagnie.
    <ul><li>Le chat dort sur le canapé.</li></ul>
  </li>
  <li>(Familier) Personne rusée.</li>
</ol>
"""

ES_HOLA_HTML = """
<h3><span class="mw-headline">Etimología</span></h3>
<p>De origen incierto, atestiguado desde el castellano medieval.</p>
<h4><span class="mw-headline">Interjección</span></h4>
<dl>
  <dt>1</dt>
  <dd>Expresión de saludo utilizada entre dos o más personas de trato familiar.
    <ul><li>Sinónimo: buenas.</li></ul>
  </dd>
  <dt>2</dt>
  <dd>Expresión de sorpresa.</dd>
</dl>
"""

IT_GATTO_HTML = """
<h3>Etimologia</h3>
<p>Dal latino tardo <i>cattus</i>.</p>
<ol>
  <li>Piccolo mammifero domestico della famiglia dei felidi.</li>
  <li>Macchina da assedio usata nel medioevo.</li>
</ol>
"""


def test_strip_tags_removes_markup_and_entities():
    assert _strip_tags("<b>Bold</b> &amp; <i>italic</i>") == "Bold & italic"


def test_extract_glosses_from_ol():
    glosses = _extract_glosses(FR_CHAT_HTML)
    assert len(glosses) == 2
    assert "Mammifère" in glosses[0]
    assert "Personne rusée" in glosses[1]
    # Nested <ul> example is stripped, not concatenated
    assert "canapé" not in glosses[0]


def test_extract_glosses_from_dl_fallback():
    glosses = _extract_glosses(ES_HOLA_HTML)
    assert len(glosses) == 2
    assert "saludo" in glosses[0].lower()
    assert "sorpresa" in glosses[1].lower()
    # Nested <ul> synonym is stripped
    assert "buenas" not in glosses[0]


def test_extract_glosses_italian_ol():
    glosses = _extract_glosses(IT_GATTO_HTML)
    assert any("mammifero" in g.lower() for g in glosses)


def test_extract_etymology_french():
    ety = _extract_etymology_from_html(FR_CHAT_HTML)
    assert ety is not None
    assert "latin" in ety.lower()


def test_extract_etymology_italian():
    ety = _extract_etymology_from_html(IT_GATTO_HTML)
    assert ety is not None
    assert "latino" in ety.lower()


def test_find_section_index_strips_span_wrappers():
    sections = [
        {"line": "Anglais", "number": "1", "index": "1"},
        {"line": "<span>Français</span>", "number": "2", "index": "5"},
    ]
    assert _find_section_index(sections, "Français") == "5"
    assert _find_section_index(sections, "Italiano") is None


def test_lookup_end_to_end_mocked(monkeypatch):
    provider = WiktionaryNativeProvider()

    def fake_sections(self, lemma, language):
        return [{"line": "<span>Français</span>", "number": "1", "index": "3"}]

    def fake_html(self, lemma, language, section):
        assert section == "3"
        return FR_CHAT_HTML

    monkeypatch.setattr(
        WiktionaryNativeProvider, "_fetch_sections", fake_sections
    )
    monkeypatch.setattr(
        WiktionaryNativeProvider, "_fetch_section_html", fake_html
    )

    entry = provider.lookup("chat", Language.FR)
    assert entry.lemma == "chat"
    assert entry.language == Language.FR
    assert entry.source == "wiktionary-native"
    assert len(entry.senses) == 2
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
        lambda self, lemma, language: [{"line": "Anglais", "index": "1"}],
    )
    with pytest.raises(LookupError, match="section"):
        provider.lookup("chat", Language.FR)


def test_lookup_raises_when_no_glosses(monkeypatch):
    provider = WiktionaryNativeProvider()
    monkeypatch.setattr(
        WiktionaryNativeProvider,
        "_fetch_sections",
        lambda self, lemma, language: [{"line": "Français", "index": "1"}],
    )
    monkeypatch.setattr(
        WiktionaryNativeProvider,
        "_fetch_section_html",
        lambda self, lemma, language, section: "<h3>Nothing here</h3><p>empty</p>",
    )
    with pytest.raises(LookupError, match="definitions"):
        provider.lookup("chat", Language.FR)
