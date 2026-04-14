"""Unit tests for WiktionaryNativeProvider.

All fetches are monkey-patched — no network, no keys.
"""

from __future__ import annotations

import pytest

from lexico.domain.enums import Language
from lexico.providers.base import LookupError
from lexico.providers.wiktionary_native_provider import (
    WiktionaryNativeProvider,
    _extract_definitions,
    _extract_derived,
    _extract_etymology_from_html,
    _extract_glosses,
    _extract_ipa,
    _extract_translations,
    _find_section_index,
    _match_pos,
    _strip_tags,
)
from lexico.domain.enums import PartOfSpeech


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


# Simplified en.wiktionary shape: ordered list of two senses where each
# <li>'s nested <ul> contains <dl><dd>citation</dd></dl> quote blocks. This
# is the structure that caused the "from stem to stern" bug where the </dl>
# would prematurely reset our nested-block state and the second sense's
# citations leaked in as ghost definitions.
EN_NESTED_DL_HTML = """
<ol>
  <li>(nautical) Over the full length of a ship.
    <ul>
      <li><div class="citation-whole">1836, Washington Irving, <i>Astoria</i></div>
        <dl><dd>From stem to stern she was coated with ice.</dd></dl>
      </li>
      <li><div class="citation-whole">1961, Time Magazine</div>
        <dl><dd>Armed from stem to stern.</dd></dl>
      </li>
    </ul>
  </li>
  <li>(idiomatic) From front to back; from one end to the other.
    <ul>
      <li><div class="citation-whole">1945, Time Magazine</div>
        <dl><dd>The kitchen was cleaned from stem to stern.</dd></dl>
      </li>
    </ul>
  </li>
</ol>
"""


def test_extract_definitions_does_not_leak_citations_as_senses():
    """Nested <dl><dd> quote blocks inside <ul> examples must not count as senses."""
    defs = _extract_definitions(EN_NESTED_DL_HTML)
    assert len(defs) == 2, f"expected 2 senses, got {[d.gloss for d in defs]}"
    assert defs[0].gloss.startswith("(nautical)")
    assert defs[1].gloss.startswith("(idiomatic)")
    # The Washington Irving / Time citation text must be absent from glosses.
    joined = " ".join(d.gloss for d in defs)
    assert "Washington Irving" not in joined
    assert "Armed from stem" not in joined
    assert "kitchen was cleaned" not in joined


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


# ---------------------------------------------------------------------------
# New rich-extraction coverage
# ---------------------------------------------------------------------------


# Abridged fr.wiktionary HTML shape for a verb section (mimics real structure).
FR_MIROITER_HTML = """
<div class="mw-heading mw-heading3"><h3 id="Verbe"><span class="titredef">Verbe</span></h3></div>
<p><b>miroiter</b> <a><span class="API" title="Prononciation API">\\mi.ʁwa.te\\</span></a> <i>intransitif</i></p>
<ol>
  <li>Jeter des <a>reflets</a>.
    <ul>
      <li><span class="example"><q><bdi lang="fr"><i>Paris miroitait aux yeux d'Emma.</i></bdi></q> <span class="sources">(<a>Flaubert</a>)</span></span></li>
    </ul>
  </li>
  <li><span class="emploi"><i>(Sens figuré)</i></span> Présenter une perspective attirante.
    <ul>
      <li><span class="example"><q><bdi lang="fr"><i>Ses promesses miroitent.</i></bdi></q> <span class="sources">(<a>Chaamba</a>)</span></span></li>
    </ul>
  </li>
</ol>
<div class="mw-heading mw-heading4"><h4 id="Dérivés">Dérivés</h4></div>
<ul><li><a title="faire miroiter">faire miroiter</a></li><li><a title="miroité">miroité</a></li></ul>
<div class="mw-heading mw-heading4"><h4 id="Traductions">Traductions</h4></div>
<div class="translations">
<ul>
<li><span data-translation-lang="en">Anglais</span> : <span class="translation"><bdi lang="en"><a>cast one's image</a></bdi></span></li>
<li><span data-translation-lang="it">Italien</span> : <span class="translation"><bdi lang="it"><a>brillare</a></bdi></span>, <span class="translation"><bdi lang="it"><a>scintillare</a></bdi></span></li>
<li><span data-translation-lang="gallo">Gallo</span> : <span class="translation"><bdi lang="gallo"><a>beluetter</a></bdi></span></li>
</ul>
</div>
"""


def test_match_pos_french_and_english():
    assert _match_pos("Verbe") == PartOfSpeech.VERB
    assert _match_pos("Nom commun") == PartOfSpeech.NOUN
    assert _match_pos("Proper noun 2") == PartOfSpeech.NOUN
    assert _match_pos("Aggettivo") == PartOfSpeech.ADJECTIVE
    assert _match_pos("Sustantivo masculino") == PartOfSpeech.NOUN
    assert _match_pos("Sillabazione") is None


def test_extract_definitions_captures_examples_and_register():
    defs = _extract_definitions(FR_MIROITER_HTML)
    assert len(defs) == 2
    assert defs[0].gloss.startswith("Jeter")
    assert defs[0].register_label is None
    assert any("Emma" in ex for ex in defs[0].examples)
    # The citation suffix must NOT leak into the example text.
    assert not any("Flaubert" in ex for ex in defs[0].examples)
    assert defs[1].register_label == "Sens figuré"
    # The register span's text must be stripped from the gloss itself.
    assert "Sens figuré" not in defs[1].gloss
    assert "perspective" in defs[1].gloss


def test_extract_ipa_accepts_valid_and_rejects_placeholder():
    html = '<span class="API">\\mi.ʁwa.te\\</span> something <span class="API">\\r\\</span>'
    assert _extract_ipa(html) == "mi.ʁwa.te"
    # A bare `\r\` placeholder should be skipped because it has no non-ASCII IPA.
    assert _extract_ipa('<span class="API">\\r\\</span>') is None


def test_extract_derived_reads_ul_links():
    block = '<ul><li><a title="faire miroiter">faire miroiter</a></li><li><a title="miroité">miroité</a></li></ul>'
    assert _extract_derived(block) == ["faire miroiter", "miroité"]


def test_extract_translations_filters_to_supported_languages():
    trans = _extract_translations(FR_MIROITER_HTML)
    assert Language.EN in trans and trans[Language.EN][0].startswith("cast")
    assert Language.IT in trans and "brillare" in trans[Language.IT]
    assert "scintillare" in trans[Language.IT]
    # Gallo is not in our supported target languages — must be dropped.
    assert all(lang in {Language.EN, Language.IT, Language.ES, Language.PT, Language.FR} for lang in trans)


def test_lookup_full_structure(monkeypatch):
    provider = WiktionaryNativeProvider()

    def fake_sections(self, lemma, language):
        return [{"line": "<span>Français</span>", "index": "1"}]

    def fake_html(self, lemma, language, section):
        return FR_MIROITER_HTML

    monkeypatch.setattr(WiktionaryNativeProvider, "_fetch_sections", fake_sections)
    monkeypatch.setattr(WiktionaryNativeProvider, "_fetch_section_html", fake_html)

    entry = provider.lookup("miroiter", Language.FR)
    assert entry.ipa == "mi.ʁwa.te"
    assert len(entry.senses) == 2
    assert entry.senses[0].part_of_speech == PartOfSpeech.VERB
    assert entry.senses[0].examples, "expected example quotes to be extracted"
    assert entry.senses[1].register_label == "Sens figuré"
    assert entry.derived == ("faire miroiter", "miroité")
    assert entry.translations[Language.EN] == ("cast one's image",)
    assert entry.translations[Language.IT] == ("brillare", "scintillare")


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
