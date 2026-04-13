"""Per-language Wiktionary provider using the MediaWiki Action API.

Hits `{lang}.wiktionary.org/w/api.php` for the page of the requested lemma,
locates the native-language section (e.g. ``Français`` on fr.wiktionary,
``Italiano`` on it.wiktionary), and extracts the definition lines in their
*own* language. This is the immersion-first complement to the old REST
provider, which always returned English glosses.

Definitions are pulled from the *rendered HTML* rather than raw wikitext.
Every Wiktionary edition renders definitions into either ``<ol><li>``
(Wikipedia-standard ordered lists, used by FR/IT/PT/EN) or ``<dl><dt><dd>``
(Spanish Wiktionary's definition-list convention). Using the rendered HTML
sidesteps per-edition wikitext quirks like Spanish ``{{impropia|...}}``
templates that hide the gloss inside a template argument.

Parsing is done with ``html.parser.HTMLParser`` rather than regex because
Wiktionary pages nest lists aggressively — each definition ``<li>`` may
contain a sub-``<ol>`` for translations, a ``<dl>`` for synonyms, an
``<ul>`` for quotations — and regex gets them wrong under nesting.
"""

from __future__ import annotations

import html
import json
import logging
import re
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from lexico.domain.enums import Language, PartOfSpeech
from lexico.domain.word import Sense, WordEntry
from lexico.providers.base import DictionaryProvider, LookupError

logger = logging.getLogger(__name__)


_USER_AGENT = "Lexico/0.1 (https://github.com/mathieucalvo/Lexico)"
_TIMEOUT_SECONDS = 8.0
_MAX_SENSES = 10


_NATIVE_SECTION: dict[Language, str] = {
    Language.FR: "Français",
    Language.IT: "Italiano",
    Language.ES: "Español",
    Language.PT: "Português",
    Language.EN: "English",
}

_WS_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(raw: str) -> str:
    """Remove HTML tags, decode entities, collapse whitespace — headings only."""
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", raw))).strip()


def _cleanup_gloss(text: str) -> str:
    """Final tidy-up on gloss strings emitted by the parsers.

    Wiktionary's ``(label)`` usage tags are rendered with spaces padding
    each token; collapse those and trim stray punctuation spacing.
    """
    text = _WS_RE.sub(" ", text).strip()
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text


class _OlGlossParser(HTMLParser):
    """Extract gloss strings from ``<ol><li>`` structures.

    Handles the nesting patterns real Wiktionary uses:

    - ``<ol class="references">`` blocks are ignored entirely (citations, not
      definitions).
    - ``<style>`` / ``<script>`` / ``<sup>`` content is ignored.
    - Nested ``<ul>`` and ``<dl>`` inside an ``<li>`` (synonyms, examples,
      quotations) are skipped so the definition comes out alone.
    - When an ``<li>`` contains a nested ``<ol>`` (the outer li is a
      category header grouping several sub-definitions), the outer li is
      dropped and the nested lis are emitted instead — so ``en:cat`` yields
      ``"A mammal of the family Felidae."`` rather than ``"Terms relating to
      animals. A mammal..."``.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.glosses: list[str] = []
        self._ol_depth = 0
        self._li_stack: list[dict[str, Any]] = []
        self._ignore_depth = 0
        self._refs_depth = 0

    def _capturing(self) -> bool:
        return (
            self._li_stack
            and self._ignore_depth == 0
            and self._refs_depth == 0
        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._refs_depth > 0:
            if tag == "ol":
                self._refs_depth += 1
            return

        if tag in ("style", "script", "sup"):
            self._ignore_depth += 1
            return

        if tag == "ol":
            cls = dict(attrs).get("class") or ""
            if "references" in cls or "mw-references" in cls:
                self._refs_depth = 1
                return
            self._ol_depth += 1
            if self._li_stack:
                self._li_stack[-1]["has_nested_ol"] = True
            return

        if tag in ("ul", "dl"):
            self._ignore_depth += 1
            return

        if tag == "li" and self._ol_depth > 0 and self._ignore_depth == 0:
            self._li_stack.append({"buffer": [], "has_nested_ol": False})

    def handle_endtag(self, tag: str) -> None:
        if self._refs_depth > 0:
            if tag == "ol":
                self._refs_depth -= 1
            return

        if tag in ("style", "script", "sup"):
            if self._ignore_depth > 0:
                self._ignore_depth -= 1
            return

        if tag in ("ul", "dl"):
            if self._ignore_depth > 0:
                self._ignore_depth -= 1
            return

        if tag == "ol":
            if self._ol_depth > 0:
                self._ol_depth -= 1
            return

        if tag == "li" and self._li_stack:
            item = self._li_stack.pop()
            if item["has_nested_ol"]:
                return
            text = _cleanup_gloss("".join(item["buffer"]))
            if text and len(text) > 2:
                self.glosses.append(text)

    def handle_data(self, data: str) -> None:
        if self._capturing():
            self._li_stack[-1]["buffer"].append(data)


class _DdGlossParser(HTMLParser):
    """Fallback extractor for Spanish Wiktionary's ``<dl><dt><dd>`` layout.

    Each ``<dd>`` directly inside a ``<dl>`` is treated as one gloss. Nested
    ``<ul>``/``<dl>``/``<ol>`` content inside the dd is skipped (synonyms,
    related terms). ``<style>`` content is skipped — without this, Spanish
    Wiktionary's inline TemplateStyles CSS leaks into the gloss string.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.glosses: list[str] = []
        self._dd_stack: list[list[str]] = []
        self._ignore_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("style", "script", "sup"):
            self._ignore_depth += 1
            return
        if tag == "dd" and self._ignore_depth == 0:
            self._dd_stack.append([])
            return
        if tag in ("ul", "ol", "dl") and self._dd_stack:
            # Nested list inside a dd is meta-content, not another definition.
            self._ignore_depth += 1
            return

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script", "sup"):
            if self._ignore_depth > 0:
                self._ignore_depth -= 1
            return
        if tag in ("ul", "ol", "dl"):
            if self._ignore_depth > 0:
                self._ignore_depth -= 1
            return
        if tag == "dd" and self._dd_stack:
            buffer = self._dd_stack.pop()
            text = _cleanup_gloss("".join(buffer))
            if text and len(text) > 2:
                self.glosses.append(text)

    def handle_data(self, data: str) -> None:
        if self._ignore_depth == 0 and self._dd_stack:
            self._dd_stack[-1].append(data)


def _extract_glosses(html_text: str) -> list[str]:
    """Pull definition strings from rendered section HTML."""
    ol_parser = _OlGlossParser()
    ol_parser.feed(html_text)
    if ol_parser.glosses:
        return ol_parser.glosses[:_MAX_SENSES]

    dd_parser = _DdGlossParser()
    dd_parser.feed(html_text)
    return dd_parser.glosses[:_MAX_SENSES]


def _extract_etymology_from_html(html_text: str) -> str | None:
    """Grab the first paragraph under an etymology heading, if present.

    Works across editions because heading text always contains one of
    ``etymo`` / ``etimo`` / ``étymo`` regardless of wrapper markup.
    """
    pattern = re.compile(
        r"<h[234][^>]*>(.*?)</h[234]>(.*?)(?=<h[234]|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    for match in pattern.finditer(html_text):
        header = _strip_tags(match.group(1)).lower()
        if not any(tok in header for tok in ("etymo", "etimo", "étymo")):
            continue
        body = match.group(2)
        for p_match in re.finditer(
            r"<p\b[^>]*>(.*?)</p>", body, re.DOTALL | re.IGNORECASE
        ):
            cleaned = _strip_tags(p_match.group(1))
            if not cleaned or len(cleaned) <= 4:
                continue
            if "lua error" in cleaned.lower() or "module:" in cleaned.lower():
                # MediaWiki occasionally ships a rendering error in place of
                # the real etymology. Don't surface it to the user.
                continue
            return cleaned
    return None


def _find_section_index(
    sections: list[dict[str, Any]], header: str
) -> str | None:
    """Return the flat ``index`` of the top-level section whose header matches.

    Section headers on FR/PT Wiktionary are wrapped in ``<span>`` tags, so we
    strip HTML before comparing. ``index`` (not ``number``) is the parameter
    the MediaWiki ``section`` arg expects — ``number`` is the dotted display
    form used by the TOC and does not round-trip correctly when a page has
    multiple top-level language sections.
    """
    target = header.strip().lower()
    for section in sections:
        line = _strip_tags(str(section.get("line", ""))).lower()
        if line == target:
            idx = section.get("index") or section.get("number")
            return str(idx) if idx is not None else None
    return None


class WiktionaryNativeProvider:
    """Immersion-first Wiktionary provider.

    Looks every word up on its own native Wiktionary edition so definitions
    and etymologies are returned in the language of the word.
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

        glosses = _extract_glosses(section_html)
        if not glosses:
            raise LookupError(
                f"No definitions extracted for {lemma!r} on "
                f"{language.value}.wiktionary.org"
            )

        etymology = _extract_etymology_from_html(section_html)

        return WordEntry(
            lemma=lemma,
            language=language,
            senses=tuple(
                Sense(gloss=g, part_of_speech=PartOfSpeech.OTHER) for g in glosses
            ),
            etymology=etymology,
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
        except Exception as exc:
            logger.warning("Wiktionary parse error on %s: %s", url, exc)
            return None


_: DictionaryProvider = WiktionaryNativeProvider()
