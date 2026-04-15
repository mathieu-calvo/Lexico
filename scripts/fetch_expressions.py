"""Fetch multi-word expressions (idioms, proverbs, locutions) from Wiktionary.

For each of our five supported languages, this script:

  1. Queries the per-language Wiktionary's MediaWiki Action API for the
     native idiom/locution category (or categories), paginating until we
     have at least `TARGET_PER_LANGUAGE` candidate page titles.
  2. Feeds each title through the project's existing
     `WiktionaryNativeProvider`, which already knows how to extract a
     native-language gloss from each per-language edition's HTML.
  3. Writes the cleaned `(title, meaning)` pairs out to
     `src/lexico/data/expressions_data.json`.

The output file is loaded at import time by `src.lexico.data.daily_pool`,
so the home view's expression-of-the-day rotation pulls from hundreds of
curated idioms per language instead of a hand-authored handful.

Run it from the repo root:

    python scripts/fetch_expressions.py              # full run, all 5 langs
    python scripts/fetch_expressions.py --lang fr    # single language
    python scripts/fetch_expressions.py --target 200 # smaller per-lang cap

Idioms live in Wiktionary (CC-BY-SA). The app ships the fetched snapshot so
the home view can render offline — no runtime network dependency.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from lexico.domain.enums import Language  # noqa: E402
from lexico.providers.base import LookupError  # noqa: E402
from lexico.providers.wiktionary_native_provider import (  # noqa: E402
    WiktionaryNativeProvider,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fetch_expressions")


OUTPUT_PATH = _REPO_ROOT / "src" / "lexico" / "data" / "expressions_data.json"
USER_AGENT = "Lexico/0.1 (https://github.com/mathieucalvo/Lexico; expression-fetcher)"
TARGET_PER_LANGUAGE = 600
API_TIMEOUT = 15.0
# Polite throttle between per-page lookups — Wiktionary is generous for
# single-digit-per-second traffic, but we don't want to look like a crawler.
LOOKUP_SLEEP_SECONDS = 0.15


# Each language's native Wiktionary categorizes multi-word expressions
# differently. French and English share a single "idioms" category;
# Italian splits by phrase type; Spanish uses a prefixed namespace.
# We deliberately skip "nominal" / "sustantiva" locution categories — those
# are dominated by technical compound nouns (species names, chemical
# compounds) that aren't real idioms. Verbal, adverbial, adjectival,
# interjective, phrase-shaped and proverbs give a clean pool.
CATEGORIES: dict[Language, tuple[str, ...]] = {
    Language.FR: (
        "Catégorie:Locutions verbales en français",
        "Catégorie:Locutions adverbiales en français",
        "Catégorie:Locutions adjectivales en français",
        "Catégorie:Locutions interjectives en français",
        "Catégorie:Locutions-phrases en français",
        "Catégorie:Proverbes en français",
    ),
    Language.EN: (
        "Category:English idioms",
        "Category:English proverbs",
    ),
    Language.IT: (
        "Categoria:Locuzioni verbali in italiano",
        "Categoria:Locuzioni avverbiali in italiano",
        "Categoria:Locuzioni aggettivali in italiano",
        "Categoria:Locuzioni interiettive in italiano",
    ),
    Language.ES: (
        "Categoría:ES:Locuciones verbales",
        "Categoría:ES:Locuciones adverbiales",
        "Categoría:ES:Locuciones adjetivas",
        "Categoría:ES:Locuciones interjectivas",
        "Categoría:ES:Refranes",
    ),
    Language.PT: (
        "Categoria:Locução verbal (Português)",
        "Categoria:Locução adverbial (Português)",
        "Categoria:Locução adjetiva (Português)",
        "Categoria:Locução interjetiva (Português)",
        "Categoria:Expressão (Português)",
    ),
}


def _api_url(lang: Language) -> str:
    return f"https://{lang.value}.wiktionary.org/w/api.php"


def _get_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=API_TIMEOUT) as resp:
        return json.loads(resp.read())


def _is_usable_title(title: str) -> bool:
    """Filter out namespaced pages, appendix lists, single-word entries."""
    if ":" in title:
        return False  # e.g. "Annexe:...", "Appendix:..."
    if " " not in title:
        return False  # must be multi-word
    if any(ch.isdigit() for ch in title[:3]):
        return False  # "101", "110 proof" — numeric noise on en.wiktionary
    if len(title) < 3 or len(title) > 120:
        return False
    return True


def fetch_category_titles(lang: Language, category: str, limit: int) -> list[str]:
    """Paginate a Wiktionary category and return up to `limit` page titles."""
    titles: list[str] = []
    cm_continue: str | None = None
    while len(titles) < limit:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category,
            "cmlimit": 500,
            "cmtype": "page",
            "format": "json",
        }
        if cm_continue:
            params["cmcontinue"] = cm_continue
        url = f"{_api_url(lang)}?{urlencode(params)}"
        try:
            data = _get_json(url)
        except (HTTPError, URLError, TimeoutError) as exc:
            logger.warning("category fetch failed for %s (%s): %s", lang.value, category, exc)
            break
        members = data.get("query", {}).get("categorymembers", [])
        for member in members:
            title = member.get("title", "")
            if _is_usable_title(title):
                titles.append(title)
                if len(titles) >= limit:
                    break
        cont = data.get("continue", {})
        cm_continue = cont.get("cmcontinue")
        if not cm_continue:
            break
    return titles


def fetch_candidate_titles(lang: Language, per_language: int) -> list[str]:
    """Gather titles across every category configured for a language."""
    seen: set[str] = set()
    titles: list[str] = []
    for category in CATEGORIES[lang]:
        remaining = max(0, per_language * 2 - len(titles))
        if remaining <= 0:
            break
        logger.info("  %s · fetching category %r", lang.value, category)
        batch = fetch_category_titles(lang, category, limit=remaining)
        for t in batch:
            if t not in seen:
                seen.add(t)
                titles.append(t)
        logger.info("    → %d unique titles so far", len(titles))
    return titles[: per_language * 2]


def extract_meaning(provider: WiktionaryNativeProvider, title: str, lang: Language) -> str | None:
    """Return a short native-language gloss for `title`, or None on failure."""
    try:
        entry = provider.lookup(title, lang)
    except LookupError:
        return None
    except Exception as exc:
        logger.debug("lookup raised for %r: %s", title, exc)
        return None
    if not entry.senses:
        return None
    gloss = (entry.senses[0].gloss or "").strip()
    if not gloss:
        return None
    if len(gloss) > 260:
        gloss = gloss[:257].rstrip() + "…"
    return gloss


def fetch_for_language(
    lang: Language, target: int, provider: WiktionaryNativeProvider
) -> list[dict[str, str]]:
    logger.info("[%s] fetching up to %d expressions", lang.value, target)
    candidates = fetch_candidate_titles(lang, per_language=target)
    logger.info("[%s] %d candidate titles gathered; resolving glosses…", lang.value, len(candidates))

    out: list[dict[str, str]] = []
    for i, title in enumerate(candidates, start=1):
        if len(out) >= target:
            break
        meaning = extract_meaning(provider, title, lang)
        if meaning:
            out.append({"text": title, "meaning": meaning})
        if i % 50 == 0:
            logger.info("  [%s] processed %d / %d — kept %d", lang.value, i, len(candidates), len(out))
        time.sleep(LOOKUP_SLEEP_SECONDS)
    logger.info("[%s] done: %d expressions with glosses", lang.value, len(out))
    return out


def write_output(data: dict[str, list[dict[str, str]]]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_meta": {
            "source": "Wiktionary per-language editions via MediaWiki Action API",
            "license": "CC-BY-SA 3.0",
            "generator": "scripts/fetch_expressions.py",
        },
        "languages": data,
    }
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    total = sum(len(v) for v in data.values())
    logger.info("wrote %s · %d expressions across %d languages", OUTPUT_PATH, total, len(data))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch expressions from Wiktionary.")
    parser.add_argument(
        "--lang",
        choices=[l.value for l in Language],
        action="append",
        help="Only fetch this language (repeatable). Default: all five.",
    )
    parser.add_argument(
        "--target",
        type=int,
        default=TARGET_PER_LANGUAGE,
        help=f"Target expressions per language (default: {TARGET_PER_LANGUAGE}).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    langs: Iterable[Language]
    if args.lang:
        langs = [Language(code) for code in args.lang]
    else:
        langs = list(Language)

    provider = WiktionaryNativeProvider()

    existing: dict[str, list[dict[str, str]]] = {}
    if OUTPUT_PATH.exists():
        try:
            payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
            existing = payload.get("languages", {})
        except json.JSONDecodeError:
            logger.warning("existing %s is not valid JSON; starting fresh", OUTPUT_PATH)

    for lang in langs:
        existing[lang.value] = fetch_for_language(lang, args.target, provider)

    write_output(existing)


if __name__ == "__main__":
    main()
