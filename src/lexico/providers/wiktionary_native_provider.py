"""Per-language Wiktionary provider using the MediaWiki Action API.

Hits ``{lang}.wiktionary.org/w/api.php`` for the page of the requested lemma,
locates the native-language section (``Français`` on fr.wiktionary, ``Italiano``
on it.wiktionary, …), and extracts structured content from the rendered HTML:

- IPA pronunciation
- Part of speech
- Numbered definitions (including usage label like "(Sens figuré)")
- Usage examples with attribution, keyed under their definition
- Etymology
- Derived forms (e.g. French "Dérivés")
- Translations into our supported target languages

Extraction is edition-aware: each Wiktionary edition uses its own HTML
conventions (French uses ``<ol><li>`` + ``<span class="example">``, Spanish
uses ``<dl><dd>`` + collapsible translation tables, etc.). The parser leans
on shared patterns where possible and falls back gracefully so that, at the
very least, definitions continue to come through on every edition even when
the richer fields (examples, translations, dérivés) aren't picked up.
"""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from lexico.domain.enums import Language, PartOfSpeech
from lexico.domain.word import Example, Sense, WordEntry
from lexico.providers.base import DictionaryProvider, LookupError

logger = logging.getLogger(__name__)


_USER_AGENT = "Lexico/0.1 (https://github.com/mathieucalvo/Lexico)"
_TIMEOUT_SECONDS = 8.0
_MAX_SENSES = 12
_MAX_EXAMPLES_PER_SENSE = 3
_MAX_DERIVED = 24
_MAX_TRANSLATIONS_PER_LANG = 4


_NATIVE_SECTION: dict[Language, str] = {
    Language.FR: "Français",
    Language.IT: "Italiano",
    Language.ES: "Español",
    Language.PT: "Português",
    Language.EN: "English",
}


# Lowercased keywords → PartOfSpeech. Longest match wins at resolution time,
# so "nom commun" beats "nom", "proper noun" beats "noun".
_POS_KEYWORDS: dict[str, PartOfSpeech] = {
    # Nouns
    "nom commun": PartOfSpeech.NOUN,
    "nom propre": PartOfSpeech.NOUN,
    "nom de famille": PartOfSpeech.NOUN,
    "proper noun": PartOfSpeech.NOUN,
    "noun": PartOfSpeech.NOUN,
    "sostantivo": PartOfSpeech.NOUN,
    "sustantivo": PartOfSpeech.NOUN,
    "substantivo": PartOfSpeech.NOUN,
    # Verbs
    "verbe": PartOfSpeech.VERB,
    "verb": PartOfSpeech.VERB,
    "verbo": PartOfSpeech.VERB,
    # Adjectives
    "adjectif": PartOfSpeech.ADJECTIVE,
    "adjective": PartOfSpeech.ADJECTIVE,
    "aggettivo": PartOfSpeech.ADJECTIVE,
    "adjetivo": PartOfSpeech.ADJECTIVE,
    # Adverbs
    "adverbe": PartOfSpeech.ADVERB,
    "adverb": PartOfSpeech.ADVERB,
    "avverbio": PartOfSpeech.ADVERB,
    "adverbio": PartOfSpeech.ADVERB,
    "advérbio": PartOfSpeech.ADVERB,
    # Pronouns
    "pronom": PartOfSpeech.PRONOUN,
    "pronoun": PartOfSpeech.PRONOUN,
    "pronome": PartOfSpeech.PRONOUN,
    "pronombre": PartOfSpeech.PRONOUN,
    # Prepositions
    "préposition": PartOfSpeech.PREPOSITION,
    "preposition": PartOfSpeech.PREPOSITION,
    "preposizione": PartOfSpeech.PREPOSITION,
    "preposición": PartOfSpeech.PREPOSITION,
    "preposição": PartOfSpeech.PREPOSITION,
    # Conjunctions
    "conjonction": PartOfSpeech.CONJUNCTION,
    "conjunction": PartOfSpeech.CONJUNCTION,
    "congiunzione": PartOfSpeech.CONJUNCTION,
    "conjunción": PartOfSpeech.CONJUNCTION,
    "conjunção": PartOfSpeech.CONJUNCTION,
    # Interjections
    "interjection": PartOfSpeech.INTERJECTION,
    "interiezione": PartOfSpeech.INTERJECTION,
    "interjección": PartOfSpeech.INTERJECTION,
    "interjeição": PartOfSpeech.INTERJECTION,
    # Determiners / articles
    "déterminant": PartOfSpeech.DETERMINER,
    "determiner": PartOfSpeech.DETERMINER,
    "article": PartOfSpeech.DETERMINER,
    "articolo": PartOfSpeech.DETERMINER,
    "artículo": PartOfSpeech.DETERMINER,
    "artigo": PartOfSpeech.DETERMINER,
}


_DERIVED_KEYWORDS = (
    "dérivés",
    "derived terms",
    "parole derivate",
    "palabras derivadas",
    "verbetes derivados",
    "termos derivados",
    "derivados",
)

_TRANSLATION_KEYWORDS = (
    "traductions",
    "translations",
    "traduzione",
    "traduzioni",
    "traducciones",
    "tradução",
    "traduções",
)

_ETYMOLOGY_KEYWORDS = ("étymologie", "etymology", "etimologia", "etimología")

_PRONUNCIATION_KEYWORDS = ("prononciation", "pronunciation", "pronuncia", "pronunciación", "pronúncia")


# Maps wiktionary language codes used in `bdi lang="xx"` / `data-translation-lang`
# and various French label strings to our Language enum.
_TARGET_LANG_CODES: dict[str, Language] = {
    "fr": Language.FR,
    "français": Language.FR,
    "francés": Language.FR,
    "francese": Language.FR,
    "francês": Language.FR,
    "french": Language.FR,
    "en": Language.EN,
    "anglais": Language.EN,
    "inglese": Language.EN,
    "inglés": Language.EN,
    "inglês": Language.EN,
    "english": Language.EN,
    "it": Language.IT,
    "italien": Language.IT,
    "italiano": Language.IT,
    "italian": Language.IT,
    "es": Language.ES,
    "espagnol": Language.ES,
    "spagnolo": Language.ES,
    "español": Language.ES,
    "espanhol": Language.ES,
    "spanish": Language.ES,
    "pt": Language.PT,
    "portugais": Language.PT,
    "portoghese": Language.PT,
    "portugués": Language.PT,
    "português": Language.PT,
    "portuguese": Language.PT,
}


_WS_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]+>")
# Elements whose *content* should be dropped before plaintexting. <sup> wraps
# reference markers like [1]; <style>/<script> wrap inline CSS/JS leaks.
_DROP_ELEMENT_RE = re.compile(
    r"<(sup|style|script)\b[^>]*>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)
_IPA_STRIP = re.compile(r"^[\s/\\\[\]]+|[\s/\\\[\]]+$")
# IPA chars we're willing to accept inside a slashed/bracketed fragment.
_IPA_BODY = re.compile(
    r"[a-zA-Zʃʒŋəɛæːˈˌθðɾɐɨɔɑɡʁχʀʎɲŋɣβɟʝɻʑʂɕʈɖɭɳɽʐʔɦ.ˑ‿\u0300-\u036f]+"
)


def _strip_tags(raw: str) -> str:
    """Remove HTML tags, decode entities, collapse whitespace.

    Drops the content of ``<sup>`` / ``<style>`` / ``<script>`` entirely —
    those elements are citation markers or inline CSS, not content the user
    wants to see.
    """
    without_drops = _DROP_ELEMENT_RE.sub(" ", raw)
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", without_drops))).strip()


def _cleanup_text(text: str) -> str:
    """Tidy-up on text extracted from mixed-content HTML."""
    text = _WS_RE.sub(" ", text).strip()
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"\s*—\s*$", "", text)
    return text.strip()


def _match_pos(header_text: str) -> PartOfSpeech | None:
    """Map a heading label like 'Nom commun' / 'Noun / Noun 1' to a PartOfSpeech."""
    low = header_text.lower().strip()
    if not low:
        return None
    # Strip leading numbering / trailing disambiguation ("Noun 2", "Sustantivo 1")
    low = re.sub(r"\s*\d+\s*$", "", low)
    # Longest-keyword match so "nom commun" wins over "nom".
    best: tuple[int, PartOfSpeech] | None = None
    for kw, pos in _POS_KEYWORDS.items():
        if kw in low:
            if best is None or len(kw) > best[0]:
                best = (len(kw), pos)
    return best[1] if best else None


def _has_keyword(header: str, keywords: Iterable[str]) -> bool:
    low = header.lower()
    return any(kw in low for kw in keywords)


def _iter_subsections(section_html: str) -> list[tuple[int, str, str]]:
    """Walk the rendered HTML and split it on h2/h3/h4 headings.

    Returns a list of ``(level, header_text, content_html)`` tuples, where
    ``content_html`` is everything between this heading and the next heading
    of any level (h2–h4).
    """
    # Use the heading open tag as a split marker. We want each chunk to start
    # with the heading itself so we can extract its text.
    pattern = re.compile(
        r"<h([234])\b[^>]*>(.*?)</h\1>(.*?)(?=<h[234]\b|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    out: list[tuple[int, str, str]] = []
    for m in pattern.finditer(section_html):
        level = int(m.group(1))
        header = _strip_tags(m.group(2))
        content = m.group(3)
        out.append((level, header, content))
    return out


# ---------------------------------------------------------------------------
# Gloss + examples extraction (POS block)
# ---------------------------------------------------------------------------


@dataclass
class _Definition:
    gloss: str
    register_label: str | None = None
    examples: list[str] = field(default_factory=list)


class _OlDefinitionParser(HTMLParser):
    """Extract definitions + inline examples from ``<ol><li>`` structures.

    Each top-level ``<ol><li>`` is a numbered sense. The parser captures:

    - the gloss text (everything directly under the li before any nested
      ``<ul>`` / ``<dl>``),
    - a register label from a leading ``<span class="emploi">`` ("Sens figuré",
      "Familier", …),
    - usage examples from ``<span class="example">`` inside nested
      ``<ul><li>`` blocks.

    Nested ``<ol>`` inside an li means the outer li is a category header and
    we should emit the inner items instead.

    State machine rules
    -------------------
    - ``li_stack`` only contains *definition* li frames. Nested ``<ul><li>``
      items (examples) do NOT push a frame; we stay on the outer definition.
    - Regions (register, example, sources-inside-example) are tracked as
      dicts on the frame with an "all tags" depth counter. When a region's
      depth hits 0 we know the closing tag for that region has been seen,
      regardless of how many nested tags sat inside it.
    """

    _SKIP_TAGS = ("style", "script", "sup")

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.definitions: list[_Definition] = []
        self._ol_depth = 0
        self._li_stack: list[dict[str, Any]] = []
        self._skip_depth = 0
        self._refs_depth = 0

    def _top(self) -> dict[str, Any] | None:
        return self._li_stack[-1] if self._li_stack else None

    def _new_frame(self) -> dict[str, Any]:
        return {
            "gloss_buf": [],
            "examples": [],
            "has_nested_ol": False,
            # Counter for ul/dl lists nested inside this definition's li.
            # >0 means we're inside the examples/notes subtree and must not
            # append to the gloss buffer. A counter is used instead of a flag
            # because the subtree itself often nests (en.wiktionary wraps each
            # citation in <ul><li><div><dl><dd>...</dd></dl>...</div></li></ul>
            # and we don't want the inner </dl> to look like we've left the
            # outer <ul>).
            "nested_block_depth": 0,
            # Register label region (usage marker at head of gloss)
            "register_buf": [],
            "register_depth": 0,  # 0 = not in region
            # Example region (a <span class="example">...</span> subtree)
            "example_buf": [],
            "example_depth": 0,  # 0 = not in region
            # Sources sub-region inside an example (citation suffix to drop)
            "sources_depth": 0,  # 0 = not in sources
        }

    def _bump_regions(self, top: dict[str, Any], delta: int) -> None:
        """Advance / unwind any active depth counters on a tag open or close."""
        if top["register_depth"] > 0:
            top["register_depth"] += delta
        if top["example_depth"] > 0:
            top["example_depth"] += delta
        if top["sources_depth"] > 0:
            top["sources_depth"] += delta

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {k: (v or "") for k, v in attrs}
        cls = attr_dict.get("class", "")

        if self._refs_depth > 0:
            if tag == "ol":
                self._refs_depth += 1
            return

        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
            return

        if tag == "ol":
            if "references" in cls or "mw-references" in cls:
                self._refs_depth = 1
                return
            self._ol_depth += 1
            if self._li_stack:
                self._li_stack[-1]["has_nested_ol"] = True
            return

        if tag in ("ul", "dl") and self._li_stack:
            # Entering a nested list inside a definition li. Gloss capture
            # halts; examples may start.
            self._li_stack[-1]["nested_block_depth"] += 1
            return

        if tag == "li":
            if self._ol_depth > 0 and self._skip_depth == 0:
                # A li inside a definition's nested <ul>/<dl> is NOT a new
                # sense — it's an example / citation container. Don't push
                # a new frame.
                if (
                    self._li_stack
                    and self._li_stack[-1]["nested_block_depth"] > 0
                ):
                    return
                self._li_stack.append(self._new_frame())
            return

        top = self._top()
        if top is None:
            return

        # Any tag open inside an active region advances that region's depth.
        self._bump_regions(top, +1)

        if tag == "span":
            # Region entry points. Only one region kicks off per starttag.
            if (
                top["example_depth"] > 0
                and top["sources_depth"] == 0
                and "sources" in cls
            ):
                # First sources span inside the current example. Its open
                # already bumped example_depth, so set sources_depth to the
                # same post-bump level; when sources_depth eventually returns
                # to 0 after closing, we'll be back in pure-example capture.
                top["sources_depth"] = 1
                return
            if (
                top["example_depth"] == 0
                and top["nested_block_depth"] > 0
                and "example" in cls
            ):
                # Undo the +1 we just added (region wasn't active yet) and
                # seed example_depth at 1 so we count from this span open.
                # _bump_regions only touches ACTIVE regions, so example_depth
                # is still 0 here — just set it.
                top["example_depth"] = 1
                top["example_buf"] = []
                return
            if (
                top["register_depth"] == 0
                and top["nested_block_depth"] == 0
                and "emploi" in cls
            ):
                top["register_depth"] = 1
                top["register_buf"] = []
                return

    def handle_endtag(self, tag: str) -> None:
        if self._refs_depth > 0:
            if tag == "ol":
                self._refs_depth -= 1
            return

        if tag in self._SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return

        if tag == "ol":
            if self._ol_depth > 0:
                self._ol_depth -= 1
            return

        if tag in ("ul", "dl") and self._li_stack:
            top = self._li_stack[-1]
            if top["nested_block_depth"] > 0:
                top["nested_block_depth"] -= 1
            if top["nested_block_depth"] == 0:
                # Left the full nested subtree; drop any stale region state.
                top["example_depth"] = 0
                top["sources_depth"] = 0
                top["example_buf"] = []
            return

        if tag == "li":
            top = self._top()
            if top is None:
                return
            if top["nested_block_depth"] > 0:
                # We're closing a nested (example/citation) li; the outer
                # definition li is still on top of the stack.
                return
            if top["has_nested_ol"]:
                self._li_stack.pop()
                return
            gloss = _cleanup_text("".join(top["gloss_buf"]))
            if gloss and len(gloss) > 2:
                register = None
                if top["register_buf"]:
                    register = _cleanup_text("".join(top["register_buf"]))
                    register = register.strip().strip("()").strip()
                    if not register:
                        register = None
                self.definitions.append(
                    _Definition(
                        gloss=gloss,
                        register_label=register,
                        examples=list(top["examples"]),
                    )
                )
            self._li_stack.pop()
            return

        top = self._top()
        if top is None:
            return

        # Decrement any active region counters on tag close.
        self._bump_regions(top, -1)

        if top["sources_depth"] == 1 and tag == "span":
            # sources_depth was 1 BEFORE we decremented (we already did above).
            # Actually after the bump it could now be 0. Check after the bump:
            pass

        # After the bump, inspect for region terminations.
        if top["example_depth"] == 0 and top["example_buf"]:
            text = _cleanup_text("".join(top["example_buf"]))
            if text and len(text) > 3:
                top["examples"].append(text)
            top["example_buf"] = []

        if top["register_depth"] == 0 and top["register_buf"]:
            # Nothing more to do here — the buffer will be drained at li end.
            pass

    def handle_data(self, data: str) -> None:
        if self._refs_depth > 0 or self._skip_depth > 0:
            return
        top = self._top()
        if top is None:
            return
        if top["register_depth"] > 0:
            top["register_buf"].append(data)
            return
        if top["example_depth"] > 0:
            if top["sources_depth"] == 0:
                top["example_buf"].append(data)
            return
        if top["nested_block_depth"] > 0:
            return
        top["gloss_buf"].append(data)


class _DlDefinitionParser(HTMLParser):
    """Fallback for Spanish Wiktionary's ``<dl><dd>`` layout.

    Each ``<dd>`` directly under a ``<dl>`` is one definition. Nested ``<ul>``
    content inside a dd is usage-meta (synonyms, related terms) and skipped.
    """

    _SKIP_TAGS = ("style", "script", "sup")

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.definitions: list[_Definition] = []
        self._dd_stack: list[list[str]] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "dd" and self._skip_depth == 0:
            self._dd_stack.append([])
            return
        if tag in ("ul", "ol", "dl") and self._dd_stack:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if tag in ("ul", "ol", "dl"):
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if tag == "dd" and self._dd_stack:
            buf = self._dd_stack.pop()
            text = _cleanup_text("".join(buf))
            if text and len(text) > 2:
                self.definitions.append(_Definition(gloss=text))

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and self._dd_stack:
            self._dd_stack[-1].append(data)


def _extract_definitions(block_html: str) -> list[_Definition]:
    """Pull (gloss, register_label, examples) tuples from a POS block."""
    ol = _OlDefinitionParser()
    ol.feed(block_html)
    if ol.definitions:
        return ol.definitions[:_MAX_SENSES]
    dl = _DlDefinitionParser()
    dl.feed(block_html)
    return dl.definitions[:_MAX_SENSES]


# Backwards-compatible helper used by existing tests that only care about
# the gloss strings.
def _extract_glosses(block_html: str) -> list[str]:
    return [d.gloss for d in _extract_definitions(block_html)]


# ---------------------------------------------------------------------------
# IPA extraction
# ---------------------------------------------------------------------------


_IPA_SPAN_RE = re.compile(
    r'<span\b[^>]*class="[^"]*\b(?:API|IPA)\b[^"]*"[^>]*>([^<]+)</span>',
    re.IGNORECASE,
)
# Generic "/ipa/" fallback: accept only fragments wrapped in / / or \ \ or [ ]
# with at least one clearly-IPA character.
_IPA_BRACKETED = re.compile(
    r"(?:/|\\|\[)([A-Za-zʃʒŋəɛæːˈˌθðɾɐɨɔɑɡʁχʀʎɲŋɣβɟʝɻʑʂɕʈɖɭɳɽʐʔɦ.ˑ‿\u0300-\u036f]{2,40})(?:/|\\|\])"
)
_NON_ASCII_IPA = re.compile(r"[ʃʒŋəɛæːˈˌθðɾɐɨɔɑɡʁχʀʎɲŋɣβɟʝɻʑʂɕʈɖɭɳɽʐʔɦ]")


def _is_valid_ipa(text: str) -> bool:
    """Reject placeholders like ``\\r\\`` or ``/p/``.

    Real IPA transcriptions always contain at least one of the characters we
    consider "clearly non-ASCII IPA" (stress marks, length marks, or a phone
    letter outside basic Latin). Page-internal placeholders used to refer to
    a single ASCII phoneme ("the two /r/ sounds") are skipped.
    """
    if not text or len(text) < 2:
        return False
    return bool(_NON_ASCII_IPA.search(text))


def _extract_ipa(block_html: str) -> str | None:
    """Best-effort IPA extraction.

    Tries ``<span class="API">`` / ``<span class="IPA">`` first (used by FR
    and IT), then falls back to any ``/.../`` or ``[...]``-wrapped fragment
    that contains at least one non-ASCII IPA character. Returns the inner
    fragment without the surrounding slashes.
    """
    for m in _IPA_SPAN_RE.finditer(block_html):
        raw = html.unescape(m.group(1))
        cleaned = _IPA_STRIP.sub("", raw).strip()
        if _is_valid_ipa(cleaned):
            return cleaned
    for m in _IPA_BRACKETED.finditer(block_html):
        cleaned = m.group(1).strip()
        if _is_valid_ipa(cleaned):
            return cleaned
    return None


# ---------------------------------------------------------------------------
# Etymology
# ---------------------------------------------------------------------------


def _extract_etymology(block_html: str) -> str | None:
    """First substantive paragraph under an etymology heading."""
    for level, header, content in _iter_subsections(block_html):
        if not _has_keyword(header, _ETYMOLOGY_KEYWORDS):
            continue
        for p_match in re.finditer(
            r"<p\b[^>]*>(.*?)</p>", content, re.DOTALL | re.IGNORECASE
        ):
            cleaned = _strip_tags(p_match.group(1))
            if not cleaned or len(cleaned) <= 4:
                continue
            if "lua error" in cleaned.lower() or "module:" in cleaned.lower():
                continue
            return cleaned
        # Some editions (Italian) inline etymology directly as text after the
        # heading, without a <p> wrapper. Fall back to stripping the whole
        # content, truncated to the first sentence-ish chunk.
        stripped = _strip_tags(content)
        if stripped and len(stripped) > 4:
            return stripped[:500]
    return None


# ---------------------------------------------------------------------------
# Derived forms
# ---------------------------------------------------------------------------


_DERIVED_LINK_RE = re.compile(
    r'<li\b[^>]*>.*?<a\b[^>]*title="([^"#]+)"[^>]*>([^<]+)</a>',
    re.DOTALL | re.IGNORECASE,
)


def _extract_derived(block_html: str) -> list[str]:
    """Pull derived-form lemmas from the first ``<ul>`` in a block.

    Uses ``title`` attributes when available (they contain the canonical
    lemma without surrounding formatting) and falls back to the link text.
    Dedupes while preserving order.
    """
    # Restrict to the block before the next heading to avoid bleeding into
    # the next subsection.
    ul_match = re.search(r"<ul\b[^>]*>(.*?)</ul>", block_html, re.DOTALL | re.IGNORECASE)
    if not ul_match:
        return []
    ul_body = ul_match.group(1)
    seen: list[str] = []
    for m in _DERIVED_LINK_RE.finditer(ul_body):
        title = _strip_tags(html.unescape(m.group(1))).strip()
        text = _strip_tags(html.unescape(m.group(2))).strip()
        candidate = title or text
        if not candidate or candidate.startswith("Wiktionnaire:"):
            continue
        if candidate not in seen:
            seen.append(candidate)
        if len(seen) >= _MAX_DERIVED:
            break
    return seen


# ---------------------------------------------------------------------------
# Translations
# ---------------------------------------------------------------------------


# fr.wiktionary: <li><span data-translation-lang="en">…</span> : <span class="translation"><bdi lang="en"><a>word</a></bdi>…</span>, <span class="translation">…</span></li>
_FR_TRANS_LI = re.compile(
    r'<li\b[^>]*>\s*<span[^>]*data-translation-lang="([a-z-]+)"[^>]*>[^<]*</span>[^:]*:\s*(.*?)</li>',
    re.DOTALL | re.IGNORECASE,
)
_FR_TRANS_TERM = re.compile(
    r'<bdi\b[^>]*lang="([a-z-]+)"[^>]*>(.*?)</bdi>',
    re.DOTALL | re.IGNORECASE,
)

# Generic fallback: any <li> with a <bdi lang="xx"> inside.
_ANY_BDI = re.compile(
    r'<li\b[^>]*>(.*?)</li>',
    re.DOTALL | re.IGNORECASE,
)


def _extract_translations(block_html: str) -> dict[Language, list[str]]:
    """Extract translations keyed by our supported Language values.

    Tries two strategies:
    1. ``data-translation-lang`` attribute (fr.wiktionary).
    2. Any ``<bdi lang="xx">`` fallback (covers pt/it which embed bdi
       attributes even inside their collapsible translation tables).
    """
    results: dict[Language, list[str]] = {}

    def _add(lang: Language, term: str) -> None:
        term = _cleanup_text(term)
        if not term:
            return
        bucket = results.setdefault(lang, [])
        if term in bucket:
            return
        if len(bucket) >= _MAX_TRANSLATIONS_PER_LANG:
            return
        bucket.append(term)

    # Strategy 1: French-style translation list
    for m in _FR_TRANS_LI.finditer(block_html):
        lang_code = m.group(1).lower()
        target = _TARGET_LANG_CODES.get(lang_code)
        if target is None:
            continue
        body = m.group(2)
        for term_match in _FR_TRANS_TERM.finditer(body):
            if _TARGET_LANG_CODES.get(term_match.group(1).lower()) != target:
                continue
            _add(target, _strip_tags(term_match.group(2)))

    if results:
        return results

    # Strategy 2: generic bdi fallback
    for li_match in _ANY_BDI.finditer(block_html):
        li_body = li_match.group(1)
        for term_match in _FR_TRANS_TERM.finditer(li_body):
            target = _TARGET_LANG_CODES.get(term_match.group(1).lower())
            if target is None:
                continue
            _add(target, _strip_tags(term_match.group(2)))

    return results


# ---------------------------------------------------------------------------
# Section-level parsing
# ---------------------------------------------------------------------------


@dataclass
class _ParsedPage:
    ipa: str | None = None
    senses: list[Sense] = field(default_factory=list)
    derived: list[str] = field(default_factory=list)
    translations: dict[Language, list[str]] = field(default_factory=dict)
    etymology: str | None = None


def _parse_section(section_html: str, language: Language) -> _ParsedPage:
    """Walk the subsections of a language section and pull structured data."""
    page = _ParsedPage()
    subsections = _iter_subsections(section_html)

    # Etymology can live anywhere in the section; search the whole block.
    page.etymology = _extract_etymology(section_html)

    # First-pass IPA from anywhere in the section (covers editions that put
    # pronunciation in a dedicated subsection).
    page.ipa = _extract_ipa(section_html)

    for level, header, content in subsections:
        # Part-of-speech block → pull definitions + examples
        pos = _match_pos(header)
        if pos is not None:
            defs = _extract_definitions(content)
            for d in defs:
                page.senses.append(
                    Sense(
                        gloss=d.gloss,
                        part_of_speech=pos,
                        examples=tuple(
                            Example(text=ex)
                            for ex in d.examples[:_MAX_EXAMPLES_PER_SENSE]
                        ),
                        register_label=d.register_label,
                    )
                )
            continue

        if _has_keyword(header, _DERIVED_KEYWORDS):
            for lemma in _extract_derived(content):
                if lemma not in page.derived and len(page.derived) < _MAX_DERIVED:
                    page.derived.append(lemma)
            continue

        if _has_keyword(header, _TRANSLATION_KEYWORDS):
            for lang, terms in _extract_translations(content).items():
                bucket = page.translations.setdefault(lang, [])
                for t in terms:
                    if t not in bucket and len(bucket) < _MAX_TRANSLATIONS_PER_LANG:
                        bucket.append(t)
            continue

    # Some editions (older FR pages, IT without class markers) don't wrap
    # definitions under a recognised POS heading. Fall back to harvesting any
    # ol/dl we find in the raw section HTML with POS=OTHER so we still return
    # something usable.
    if not page.senses:
        for d in _extract_definitions(section_html):
            page.senses.append(
                Sense(
                    gloss=d.gloss,
                    part_of_speech=PartOfSpeech.OTHER,
                    examples=tuple(
                        Example(text=ex)
                        for ex in d.examples[:_MAX_EXAMPLES_PER_SENSE]
                    ),
                    register_label=d.register_label,
                )
            )

    return page


# Backwards-compat shim for tests that import the old section lookup helper.
def _find_section_index(
    sections: list[dict[str, Any]], header: str
) -> str | None:
    target = header.strip().lower()
    for section in sections:
        line = _strip_tags(str(section.get("line", ""))).lower()
        if line == target:
            idx = section.get("index") or section.get("number")
            return str(idx) if idx is not None else None
    return None


# Backwards-compat shim retained for existing tests.
def _extract_etymology_from_html(block_html: str) -> str | None:
    return _extract_etymology(block_html)


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class WiktionaryNativeProvider:
    """Immersion-first Wiktionary provider.

    Fetches each word from its own native Wiktionary edition so definitions,
    examples, and etymology come back in the language of the word.
    """

    def __init__(
        self,
        timeout: float = _TIMEOUT_SECONDS,
        user_agent: str = _USER_AGENT,
    ) -> None:
        self._timeout = timeout
        self._user_agent = user_agent

    @property
    def name(self) -> str:
        return "wiktionary"

    def lookup(self, lemma: str, language: Language) -> WordEntry:
        native_header = _NATIVE_SECTION.get(language)
        if native_header is None:
            raise LookupError(f"Unsupported language {language.value!r}")

        sections = self._fetch_sections(lemma, language)
        if not sections:
            raise LookupError(f"Wiktionary returned no page for {lemma!r}")

        section_index = _find_section_index(sections, native_header)
        if section_index is None:
            raise LookupError(
                f"No {language.display_name} section for {lemma!r} on "
                f"{language.value}.wiktionary.org"
            )

        section_html = self._fetch_section_html(lemma, language, section_index)
        if not section_html:
            raise LookupError(f"Empty section HTML for {lemma!r}")

        parsed = _parse_section(section_html, language)

        if not parsed.senses:
            raise LookupError(
                f"No definitions extracted for {lemma!r} on "
                f"{language.value}.wiktionary.org"
            )

        translations = {
            lang: tuple(terms)
            for lang, terms in parsed.translations.items()
            if lang != language and terms
        }

        return WordEntry(
            lemma=lemma,
            language=language,
            ipa=parsed.ipa,
            senses=tuple(parsed.senses),
            translations=translations,
            derived=tuple(parsed.derived),
            etymology=parsed.etymology,
            source="wiktionary-native",
        )

    def random_lemma(self, language: Language) -> str | None:
        return None

    def _fetch_sections(
        self, lemma: str, language: Language
    ) -> list[dict[str, Any]] | None:
        params = {
            "action": "parse",
            "page": lemma,
            "prop": "sections",
            "format": "json",
            "redirects": "1",
        }
        data = self._api_get(language, params)
        if data is None:
            return None
        return ((data.get("parse") or {}).get("sections")) or []

    def _fetch_section_html(
        self, lemma: str, language: Language, section: str
    ) -> str | None:
        params = {
            "action": "parse",
            "page": lemma,
            "prop": "text",
            "section": section,
            "format": "json",
            "redirects": "1",
            "disabletoc": "1",
            "disableeditsection": "1",
        }
        data = self._api_get(language, params)
        if data is None:
            return None
        text = (data.get("parse") or {}).get("text") or {}
        if isinstance(text, dict):
            return text.get("*")
        return None

    def _api_get(
        self, language: Language, params: dict[str, str]
    ) -> dict[str, Any] | None:
        url = f"https://{language.value}.wiktionary.org/w/api.php?{urlencode(params)}"
        req = Request(
            url,
            headers={
                "User-Agent": self._user_agent,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 404:
                return None
            logger.warning("Wiktionary HTTP %s on %s", exc.code, url)
            return None
        except URLError as exc:
            logger.warning("Wiktionary network error on %s: %s", url, exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Wiktionary parse error on %s: %s", url, exc)
            return None


_: DictionaryProvider = WiktionaryNativeProvider()
