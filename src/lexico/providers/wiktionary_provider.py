"""Wiktionary REST API dictionary provider.

Uses the MediaWiki REST endpoint at
`https://en.wiktionary.org/api/rest_v1/page/definition/{word}`, which
returns structured JSON for every language section that appears on the
English Wiktionary page for a given lemma. Free, no API key, no bulk
download. Each network hit is cached indefinitely in SQLite by
LookupService, so every word is fetched at most once per user.
"""

from __future__ import annotations

import html
import json
import logging
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from lexico.domain.enums import Language, PartOfSpeech
from lexico.domain.word import Example, Sense, WordEntry
from lexico.providers.base import DictionaryProvider, LookupError

logger = logging.getLogger(__name__)


_API_BASE = "https://en.wiktionary.org/api/rest_v1/page/definition/"
_USER_AGENT = "Lexico/0.1 (https://github.com/mathieucalvo/Lexico)"
_TIMEOUT_SECONDS = 8.0
_MAX_SENSES = 10

_POS_MAP: dict[str, PartOfSpeech] = {
    "noun": PartOfSpeech.NOUN,
    "proper noun": PartOfSpeech.NOUN,
    "verb": PartOfSpeech.VERB,
    "adjective": PartOfSpeech.ADJECTIVE,
    "adverb": PartOfSpeech.ADVERB,
    "pronoun": PartOfSpeech.PRONOUN,
    "preposition": PartOfSpeech.PREPOSITION,
    "conjunction": PartOfSpeech.CONJUNCTION,
    "interjection": PartOfSpeech.INTERJECTION,
    "determiner": PartOfSpeech.DETERMINER,
    "article": PartOfSpeech.DETERMINER,
    "phrase": PartOfSpeech.PHRASE,
}


class _HtmlStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    @property
    def text(self) -> str:
        return "".join(self._parts)


def _strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    stripper = _HtmlStripper()
    try:
        stripper.feed(raw)
        out = stripper.text
    except Exception:
        out = raw
    return html.unescape(out).strip()


def _to_pos(label: str | None) -> PartOfSpeech:
    if not label:
        return PartOfSpeech.OTHER
    return _POS_MAP.get(label.strip().lower(), PartOfSpeech.OTHER)


def _extract_examples(definition: dict[str, Any]) -> tuple[Example, ...]:
    """Wiktionary's payload puts examples under either `examples` (HTML strings)
    or `parsedExamples` (list of dicts). Accept whichever is present.
    """
    out: list[Example] = []
    for ex in definition.get("examples") or []:
        if isinstance(ex, str):
            text = _strip_html(ex)
            if text:
                out.append(Example(text=text))
    for ex in definition.get("parsedExamples") or []:
        if isinstance(ex, dict):
            text = _strip_html(ex.get("example"))
            if text:
                out.append(Example(text=text))
        elif isinstance(ex, str):
            text = _strip_html(ex)
            if text:
                out.append(Example(text=text))
    return tuple(out[:3])


class WiktionaryProvider:
    """Live Wiktionary REST API dictionary provider.

    Hits en.wiktionary.org for the JSON definition payload, filters to
    the requested language section, and builds a WordEntry. Missing IPA,
    etymology, and translations degrade gracefully — the UI already
    handles empty fields.
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
        payload = self._fetch(lemma)
        if payload is None:
            raise LookupError(f"Wiktionary returned no data for {lemma!r}")

        sections = payload.get(language.value) or payload.get(language.value.lower())
        if not sections:
            raise LookupError(
                f"No {language.display_name} entry for {lemma!r} on Wiktionary"
            )

        senses: list[Sense] = []
        for section in sections:
            pos = _to_pos(section.get("partOfSpeech"))
            for definition in section.get("definitions") or []:
                gloss = _strip_html(definition.get("definition"))
                if not gloss:
                    continue
                senses.append(
                    Sense(
                        gloss=gloss,
                        part_of_speech=pos,
                        examples=_extract_examples(definition),
                    )
                )
                if len(senses) >= _MAX_SENSES:
                    break
            if len(senses) >= _MAX_SENSES:
                break

        if not senses:
            raise LookupError(
                f"No parseable senses for {lemma!r} in {language.value}"
            )

        return WordEntry(
            lemma=lemma,
            language=language,
            senses=tuple(senses),
            source="wiktionary",
        )

    def random_lemma(self, language: Language) -> str | None:
        return None

    def _fetch(self, lemma: str) -> dict[str, Any] | None:
        url = _API_BASE + quote(lemma, safe="")
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
            logger.warning("Wiktionary HTTP %s for %r", exc.code, lemma)
            return None
        except URLError as exc:
            logger.warning("Wiktionary network error for %r: %s", lemma, exc)
            return None
        except Exception as exc:
            logger.warning("Wiktionary parse error for %r: %s", lemma, exc)
            return None


_: DictionaryProvider = WiktionaryProvider()
