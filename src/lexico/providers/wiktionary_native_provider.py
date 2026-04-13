"""Per-language Wiktionary provider using the MediaWiki Action API.

Hits `{lang}.wiktionary.org/w/api.php` for the page of the requested lemma,
locates the native-language section (e.g. ``Français`` on fr.wiktionary,
``Italiano`` on it.wiktionary), and extracts the definition lines in their
*own* language. This is the immersion-first complement to the old REST
provider, which always returned English glosses.

Definitions come from wikitext `# ...` list items, which is the universal
gloss marker across every Wiktionary edition. Templates, wiki-links, bold
and italic markers, and refs are stripped with a small regex cleaner.
"""

from __future__ import annotations

import json
import logging
import re
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

_ETYMOLOGY_HEADERS: dict[Language, tuple[str, ...]] = {
    Language.FR: ("Étymologie", "Etymologie"),
    Language.IT: ("Etimologia",),
    Language.ES: ("Etimología",),
    Language.PT: ("Etimologia",),
    Language.EN: ("Etymology",),
}


def _clean_wikitext(raw: str) -> str:
    """Strip wikitext markup down to readable prose.

    Handles the common cases: templates, wiki-links, bold/italic, refs,
    HTML comments. Nested templates are unwound in a loop.
    """
    text = raw
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<ref[^>]*?/>", "", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)

    # Collapse templates {{...}}. Loop because of nesting.
    for _ in range(5):
        new = re.sub(r"\{\{[^{}]*\}\}", "", text)
        if new == text:
            break
        text = new

    # [[target|label]] -> label ; [[target]] -> target
    text = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]+)\]\]", r"\1", text)

    # '''bold''' and ''italic''
    text = re.sub(r"'{2,5}", "", text)

    # Remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Leading list markers / colons
    text = re.sub(r"^[#*:;]+\s*", "", text)

    return re.sub(r"\s+", " ", text).strip()


def _extract_glosses(section_wikitext: str) -> list[str]:
    """Pull gloss lines from a section's raw wikitext.

    Each `# ...` line (but not `##` sub-examples or `#:` quotations) is a
    definition. We cap before cleaning so pathological pages don't balloon.
    """
    glosses: list[str] = []
    for line in section_wikitext.splitlines():
        stripped = line.lstrip()
        if not stripped.startswith("#"):
            continue
        # Skip examples (#:), quotations (#*), nested markers
        marker_end = 0
        for ch in stripped:
            if ch == "#":
                marker_end += 1
            else:
                break
        if marker_end != 1:
            continue
        after = stripped[1:].lstrip()
        if after.startswith((":", "*")):
            continue
        cleaned = _clean_wikitext(after)
        if cleaned and len(cleaned) > 1:
            glosses.append(cleaned)
            if len(glosses) >= _MAX_SENSES:
                break
    return glosses


def _extract_etymology(section_wikitext: str, headers: tuple[str, ...]) -> str | None:
    """Best-effort etymology lookup within a language section."""
    lines = section_wikitext.splitlines()
    for idx, line in enumerate(lines):
        if not line.lstrip().startswith("="):
            continue
        header_text = line.strip().strip("=").strip()
        if not any(h.lower() in header_text.lower() for h in headers):
            continue
        for body in lines[idx + 1 :]:
            stripped = body.strip()
            if not stripped:
                continue
            if stripped.startswith("="):
                break
            cleaned = _clean_wikitext(stripped)
            if cleaned and len(cleaned) > 3:
                return cleaned
    return None


class WiktionaryNativeProvider:
    """Immersion-first Wiktionary provider.

    Looks every word up on its own native Wiktionary edition so that
    definitions and etymologies are returned in the language of the word.
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

        section_number = _find_section(sections, native_header)
        if section_number is None:
            raise LookupError(
                f"No {language.display_name} section for {lemma!r} on "
                f"{language.value}.wiktionary.org"
            )

        wikitext = self._fetch_wikitext(lemma, language, section_number)
        if not wikitext:
            raise LookupError(f"Empty wikitext for {lemma!r}")

        glosses = _extract_glosses(wikitext)
        if not glosses:
            raise LookupError(
                f"No definitions extracted for {lemma!r} on "
                f"{language.value}.wiktionary.org"
            )

        etymology = _extract_etymology(wikitext, _ETYMOLOGY_HEADERS[language])

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

    def _fetch_wikitext(
        self, lemma: str, language: Language, section: str
    ) -> str | None:
        params = {
            "action": "parse",
            "page": lemma,
            "prop": "wikitext",
            "section": section,
            "format": "json",
            "redirects": "1",
        }
        data = self._api_get(language, params)
        if data is None:
            return None
        wikitext = (data.get("parse") or {}).get("wikitext") or {}
        if isinstance(wikitext, dict):
            return wikitext.get("*")
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


def _find_section(sections: list[dict[str, Any]], header: str) -> str | None:
    """Return the `number` of the top-level section whose `line` matches."""
    target = header.strip().lower()
    for section in sections:
        line = str(section.get("line", "")).strip().lower()
        if line == target:
            return str(section.get("number") or section.get("index") or "")
    return None


_: DictionaryProvider = WiktionaryNativeProvider()
