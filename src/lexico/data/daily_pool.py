"""Daily pools: word-of-the-day, expression, and quote per language.

Two kinds of content live here:

- **Word** and **quote** pools are hand-authored Python literals — small,
  curated, and carefully picked so they always look good on the home page.
- **Expression** pools are larger (hundreds per language) and are harvested
  from Wiktionary by ``scripts/fetch_expressions.py``. The script writes a
  snapshot to ``expressions_data.json`` next to this module, which is
  loaded once at import time. If the snapshot is missing (e.g. the fetch
  has never been run), a tiny hand-authored fallback keeps the home view
  working so the app is never broken.

The home view pulls one item per pool per day, indexed deterministically
by date so every user sees the same thing on the same day without needing
a database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from lexico.domain.enums import Language, PartOfSpeech
from lexico.domain.word import Sense, WordEntry


@dataclass(frozen=True)
class DailyExpression:
    text: str
    meaning: str


@dataclass(frozen=True)
class DailyQuote:
    text: str
    author: str


# Word-of-the-day pools — common, learner-friendly lemmas that are likely to
# be found in Wiktionary. The home view passes each to the lookup service.
WORD_POOLS: dict[Language, tuple[str, ...]] = {
    Language.FR: (
        "éphémère", "flâner", "chuchoter", "sérendipité", "crépuscule",
        "tendresse", "bienveillance", "fulgurance", "mélancolie", "paisible",
        "lumineux", "épanouir", "murmurer", "ruisseau", "brume",
        "clairière", "douceur", "ivresse", "songer", "scintiller",
    ),
    Language.EN: (
        "serendipity", "ephemeral", "petrichor", "luminous", "wistful",
        "solitude", "whisper", "meander", "twilight", "resilient",
        "linger", "radiant", "tranquil", "saunter", "dwell",
        "fleeting", "gentle", "vivid", "glimmer", "mellow",
    ),
    Language.IT: (
        "meraviglia", "effimero", "passeggiare", "crepuscolo", "dolcezza",
        "sussurrare", "luminoso", "nostalgia", "sereno", "incantevole",
        "silenzio", "ruscello", "splendere", "vagare", "tenerezza",
        "brezza", "sognare", "fulgore", "chiarore", "quiete",
    ),
    Language.ES: (
        "duende", "efímero", "pasear", "crepúsculo", "anhelar",
        "susurro", "luminoso", "nostalgia", "sereno", "entrañable",
        "ternura", "brillar", "vagar", "dulzura", "silencio",
        "arroyo", "soñar", "fulgor", "claridad", "calma",
    ),
    Language.PT: (
        "saudade", "efêmero", "passear", "crepúsculo", "sussurro",
        "luminoso", "ternura", "silêncio", "sereno", "brilhar",
        "vagar", "doçura", "riacho", "sonhar", "brisa",
        "fulgor", "clareira", "calma", "anseio", "encanto",
    ),
}


# Fallback expression pool used only if the Wiktionary-sourced JSON snapshot
# is missing. Small and hand-authored — enough to keep the home view
# rendering something reasonable while the fetch script hasn't been run.
_FALLBACK_EXPRESSIONS: dict[Language, tuple[DailyExpression, ...]] = {
    Language.FR: (
        DailyExpression("coûter les yeux de la tête", "Être extrêmement cher."),
        DailyExpression("poser un lapin", "Ne pas venir à un rendez-vous."),
        DailyExpression("tomber dans les pommes", "S'évanouir."),
        DailyExpression("jeter l'éponge", "Abandonner, renoncer."),
    ),
    Language.EN: (
        DailyExpression("break the ice", "Start a conversation in an awkward moment."),
        DailyExpression("a piece of cake", "Something very easy."),
        DailyExpression("burn the midnight oil", "Work late into the night."),
        DailyExpression("once in a blue moon", "Very rarely."),
    ),
    Language.IT: (
        DailyExpression("in bocca al lupo", "Formula per augurare buona fortuna."),
        DailyExpression("rompere il ghiaccio", "Iniziare una conversazione in un momento imbarazzante."),
        DailyExpression("essere al settimo cielo", "Essere felicissimo."),
        DailyExpression("costare un occhio della testa", "Essere molto caro."),
    ),
    Language.ES: (
        DailyExpression("tomar el pelo", "Burlarse de alguien, engañarlo en broma."),
        DailyExpression("ser pan comido", "Ser muy fácil."),
        DailyExpression("costar un ojo de la cara", "Ser muy caro."),
        DailyExpression("meter la pata", "Cometer un error."),
    ),
    Language.PT: (
        DailyExpression("engolir sapos", "Tolerar coisas desagradáveis em silêncio."),
        DailyExpression("pagar o pato", "Levar a culpa por algo que não fez."),
        DailyExpression("custar os olhos da cara", "Ser muito caro."),
        DailyExpression("quebrar o galho", "Dar um jeito provisório para ajudar."),
    ),
}


_EXPRESSIONS_JSON_PATH = Path(__file__).with_name("expressions_data.json")


def _load_expression_pools() -> dict[Language, tuple[DailyExpression, ...]]:
    """Load the Wiktionary snapshot, falling back to hand-authored data.

    The snapshot is produced by ``scripts/fetch_expressions.py`` and lives
    alongside this module as ``expressions_data.json``. If it's absent or
    unparseable, we use ``_FALLBACK_EXPRESSIONS`` so the home view never
    breaks — the app just renders fewer idioms until the script is re-run.
    """
    if not _EXPRESSIONS_JSON_PATH.exists():
        return dict(_FALLBACK_EXPRESSIONS)
    try:
        payload = json.loads(_EXPRESSIONS_JSON_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(_FALLBACK_EXPRESSIONS)

    raw = payload.get("languages", {})
    out: dict[Language, tuple[DailyExpression, ...]] = {}
    for lang in Language:
        items = raw.get(lang.value) or []
        pool = tuple(
            DailyExpression(text=item["text"], meaning=item["meaning"])
            for item in items
            if item.get("text") and item.get("meaning")
        )
        if not pool:
            pool = _FALLBACK_EXPRESSIONS.get(lang, ())
        out[lang] = pool
    return out


EXPRESSION_POOLS: dict[Language, tuple[DailyExpression, ...]] = _load_expression_pools()


# Quotes — short aphorisms by well-known authors in each language.
QUOTE_POOLS: dict[Language, tuple[DailyQuote, ...]] = {
    Language.FR: (
        DailyQuote("On ne voit bien qu'avec le cœur. L'essentiel est invisible pour les yeux.", "Antoine de Saint-Exupéry"),
        DailyQuote("Le bonheur, c'est de continuer à désirer ce que l'on possède.", "Saint Augustin"),
        DailyQuote("Je pense, donc je suis.", "René Descartes"),
        DailyQuote("L'enfer, c'est les autres.", "Jean-Paul Sartre"),
        DailyQuote("Rien ne sert de courir, il faut partir à point.", "Jean de La Fontaine"),
        DailyQuote("La vie est un sommeil, l'amour en est le rêve.", "Alfred de Musset"),
        DailyQuote("Aimer, ce n'est pas se regarder l'un l'autre, c'est regarder ensemble dans la même direction.", "Antoine de Saint-Exupéry"),
    ),
    Language.EN: (
        DailyQuote("To be, or not to be, that is the question.", "William Shakespeare"),
        DailyQuote("The only way to do great work is to love what you do.", "Steve Jobs"),
        DailyQuote("In the middle of every difficulty lies opportunity.", "Albert Einstein"),
        DailyQuote("We are what we repeatedly do. Excellence, then, is not an act, but a habit.", "Will Durant"),
        DailyQuote("Not all those who wander are lost.", "J.R.R. Tolkien"),
        DailyQuote("The journey of a thousand miles begins with a single step.", "Lao Tzu"),
        DailyQuote("Whether you think you can, or you think you can't — you're right.", "Henry Ford"),
    ),
    Language.IT: (
        DailyQuote("Nel mezzo del cammin di nostra vita mi ritrovai per una selva oscura.", "Dante Alighieri"),
        DailyQuote("La vita è come andare in bicicletta: per mantenere l'equilibrio devi muoverti.", "Albert Einstein"),
        DailyQuote("Chi non fa, non sbaglia.", "Proverbio italiano"),
        DailyQuote("L'amor che move il sole e l'altre stelle.", "Dante Alighieri"),
        DailyQuote("Ogni cosa è illuminata dalla luce di coloro che la guardano con amore.", "Italo Calvino"),
        DailyQuote("La semplicità è la sofisticazione suprema.", "Leonardo da Vinci"),
        DailyQuote("Chi ha un perché nella vita può sopportare quasi ogni come.", "Friedrich Nietzsche"),
    ),
    Language.ES: (
        DailyQuote("En un lugar de la Mancha, de cuyo nombre no quiero acordarme…", "Miguel de Cervantes"),
        DailyQuote("Caminante, no hay camino, se hace camino al andar.", "Antonio Machado"),
        DailyQuote("Solo sé que no sé nada.", "Sócrates"),
        DailyQuote("La vida es sueño, y los sueños, sueños son.", "Pedro Calderón de la Barca"),
        DailyQuote("Hoy es siempre todavía.", "Antonio Machado"),
        DailyQuote("Cualquier tiempo pasado fue mejor.", "Jorge Manrique"),
        DailyQuote("Poderoso caballero es don Dinero.", "Francisco de Quevedo"),
    ),
    Language.PT: (
        DailyQuote("Tudo vale a pena se a alma não é pequena.", "Fernando Pessoa"),
        DailyQuote("Navegar é preciso, viver não é preciso.", "Fernando Pessoa"),
        DailyQuote("A vida é a arte do encontro, embora haja tantos desencontros pela vida.", "Vinicius de Moraes"),
        DailyQuote("O que é amar senão compreender e associar-se à exaltação de outro ser?", "Machado de Assis"),
        DailyQuote("Quem não tem cão caça com gato.", "Provérbio português"),
        DailyQuote("A saudade é o amor que fica.", "Fernando Pessoa"),
        DailyQuote("Tudo no mundo começou com um sim.", "Clarice Lispector"),
    ),
}


def _day_index(language: Language, pool_size: int, today: date | None, salt: int) -> int:
    """Deterministic index into a pool of size `pool_size` for `today`.

    Different `salt` values let WotD / expression / quote advance on
    independent cycles, so all three don't roll together in lockstep.
    """
    if pool_size <= 0:
        return 0
    t = today or datetime.now(timezone.utc).date()
    offset = {
        Language.FR: 0,
        Language.EN: 7,
        Language.IT: 13,
        Language.ES: 23,
        Language.PT: 31,
    }[language]
    return (t.toordinal() + offset + salt) % pool_size


def word_of_the_day(language: Language, today: date | None = None) -> str | None:
    pool = WORD_POOLS.get(language, ())
    if not pool:
        return None
    return pool[_day_index(language, len(pool), today, salt=0)]


def expression_of_the_day(language: Language, today: date | None = None) -> DailyExpression | None:
    pool = EXPRESSION_POOLS.get(language, ())
    if not pool:
        return None
    return pool[_day_index(language, len(pool), today, salt=101)]


def quote_of_the_day(language: Language, today: date | None = None) -> DailyQuote | None:
    pool = QUOTE_POOLS.get(language, ())
    if not pool:
        return None
    return pool[_day_index(language, len(pool), today, salt=211)]


def expression_to_word_entry(
    expression: DailyExpression, language: Language
) -> WordEntry:
    """Wrap a DailyExpression as a WordEntry so it can be saved as a Card.

    Home's "save this expression" button flows the idiom through the same
    Card/FSRS/review pipeline as any other lemma. The expression text
    becomes the lemma and its meaning becomes the single sense's gloss,
    marked as a PHRASE so the review view renders it cleanly.
    """
    return WordEntry(
        lemma=expression.text,
        language=language,
        senses=(
            Sense(
                gloss=expression.meaning,
                part_of_speech=PartOfSpeech.PHRASE,
            ),
        ),
        source="wiktionary-expression",
    )
