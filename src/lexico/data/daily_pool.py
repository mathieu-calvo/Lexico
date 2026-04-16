"""Daily pools: word-of-the-day, expression, and quote per language.

Three kinds of content live here:

- **Word** pools are hand-authored Python literals — 100+ rare/evocative
  lemmas per language.
- **Quote** pools live in ``quotes_data.json`` next to this module and are
  loaded at import time. A tiny hand-authored fallback keeps the home
  view working if the snapshot is missing or unparseable.
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


# Word-of-the-day pools — rare, evocative, learner-stretching lemmas that
# should resolve in Wiktionary. Each pool is 100+ entries so the daily
# rotation stays fresh for months before it loops.
WORD_POOLS: dict[Language, tuple[str, ...]] = {
    Language.FR: (
        "éphémère", "flâner", "chuchoter", "sérendipité", "crépuscule",
        "tendresse", "bienveillance", "fulgurance", "mélancolie", "paisible",
        "lumineux", "épanouir", "murmurer", "ruisseau", "brume",
        "clairière", "douceur", "ivresse", "songer", "scintiller",
        "onirique", "résonance", "chimère", "palimpseste", "enchanteur",
        "évanescent", "velouté", "pétillant", "effluve", "aurore",
        "frisson", "nacré", "suranné", "sépulcral", "quintessence",
        "mirifique", "indicible", "pudeur", "effroi", "languissant",
        "incandescent", "diaphane", "crépusculaire", "ténèbres", "funeste",
        "méandre", "abîme", "litanie", "réminiscence", "ressac",
        "irisé", "hiératique", "mystère", "liminaire", "phosphorescent",
        "impromptu", "mutique", "tellurique", "féerie", "sibyllin",
        "halo", "volute", "subjuguer", "désinvolture", "arabesque",
        "étincelle", "pérenne", "mirage", "cristallin", "limpide",
        "luxuriant", "nonchalant", "pourpre", "vespéral", "crépiter",
        "ciseler", "arcane", "vertige", "brouhaha", "gouffre",
        "jubilation", "fugace", "plénitude", "tressaillir", "saltimbanque",
        "luciole", "aube", "rosée", "nacre", "caresse",
        "émoi", "silhouette", "embrun", "givre", "pétale",
        "horizon", "sillage", "lueur", "ombre", "clarté",
        "souffle", "zénith", "baroque", "berceau", "muse",
        "clameur", "mystérieux",
    ),
    Language.EN: (
        "serendipity", "ephemeral", "petrichor", "luminous", "wistful",
        "solitude", "whisper", "meander", "twilight", "resilient",
        "linger", "radiant", "tranquil", "saunter", "dwell",
        "fleeting", "gentle", "vivid", "glimmer", "mellow",
        "ethereal", "sonorous", "labyrinth", "reverie", "susurrus",
        "lambent", "incandescent", "halcyon", "eloquent", "ineffable",
        "liminal", "crepuscular", "phosphorescence", "iridescent", "oblivion",
        "whimsical", "nostalgia", "solace", "quintessence", "ineluctable",
        "evanescent", "vestige", "chimera", "zephyr", "mirage",
        "tessellate", "diaphanous", "scintillate", "shimmer", "billow",
        "cascade", "pellucid", "resplendent", "august", "silhouette",
        "gossamer", "palimpsest", "verdant", "tenebrous", "sylvan",
        "arcane", "nebulous", "fathom", "bastion", "cacophony",
        "clandestine", "elegy", "filigree", "harbinger", "juxtapose",
        "limpid", "luminary", "mercurial", "nocturnal", "opulent",
        "pantheon", "quixotic", "rapturous", "rhapsody", "saturnine",
        "taciturn", "umbra", "vignette", "whimsy", "yonder",
        "zenith", "bewilder", "gumption", "myriad", "obfuscate",
        "panacea", "supine", "threnody", "ubiquitous", "voluble",
        "winsome", "yearn", "placid", "verdure", "murmur",
        "rustle", "kindle", "cerulean", "chiaroscuro", "dappled",
        "effervescent", "ephemerality",
    ),
    Language.IT: (
        "meraviglia", "effimero", "passeggiare", "crepuscolo", "dolcezza",
        "sussurrare", "luminoso", "nostalgia", "sereno", "incantevole",
        "silenzio", "ruscello", "splendere", "vagare", "tenerezza",
        "brezza", "sognare", "fulgore", "chiarore", "quiete",
        "abisso", "arcano", "etereo", "onirico", "labirinto",
        "palpito", "chimera", "miraggio", "diafano", "scintillare",
        "luccicare", "fruscio", "stormire", "vagheggiare", "inebriare",
        "crepuscolare", "fosforescente", "iridescente", "oblio", "solitudine",
        "quintessenza", "evanescente", "rimembranza", "risacca", "misterioso",
        "preludio", "tellurico", "fatato", "sibillino", "alone",
        "spirale", "soggiogare", "noncuranza", "arabesco", "scintilla",
        "perenne", "cristallino", "limpido", "lussureggiante", "disinvolto",
        "porpora", "crepitare", "cesellare", "vertigine", "brusio",
        "baratro", "giubilo", "fugace", "pienezza", "trasalire",
        "saltimbanco", "lucciola", "alba", "rugiada", "madreperla",
        "carezza", "emozione", "spruzzo", "brina", "petalo",
        "orizzonte", "scia", "bagliore", "ombra", "chiarezza",
        "soffio", "zenit", "barocco", "culla", "sfumatura",
        "incenso", "gemma", "nido", "brama", "veglia",
        "canto", "raggio", "riflesso", "lirico", "vibrare",
        "ruggire", "melodia", "armonia", "stupore", "ineffabile",
    ),
    Language.ES: (
        "duende", "efímero", "pasear", "crepúsculo", "anhelar",
        "susurro", "luminoso", "nostalgia", "sereno", "entrañable",
        "ternura", "brillar", "vagar", "dulzura", "silencio",
        "arroyo", "soñar", "fulgor", "claridad", "calma",
        "arcano", "abismo", "onírico", "laberinto", "palpitar",
        "resplandor", "quimera", "espejismo", "diáfano", "centellear",
        "destellar", "rumor", "murmullo", "embriagar", "crepuscular",
        "fosforescente", "iridiscente", "olvido", "soledad", "quintaesencia",
        "evanescente", "reminiscencia", "resaca", "misterioso", "preludio",
        "telúrico", "encantado", "sibilino", "halo", "espiral",
        "subyugar", "indolencia", "arabesco", "chispa", "perenne",
        "cristalino", "límpido", "exuberante", "desenvuelto", "púrpura",
        "vespertino", "crepitar", "cincelar", "vértigo", "bullicio",
        "júbilo", "fugaz", "plenitud", "estremecer", "saltimbanqui",
        "luciérnaga", "alba", "rocío", "nácar", "caricia",
        "emoción", "silueta", "espuma", "escarcha", "pétalo",
        "horizonte", "estela", "destello", "sombra", "soplo",
        "zenit", "barroco", "cuna", "matiz", "incienso",
        "joya", "nido", "añoranza", "vigilia", "canto",
        "rayo", "reflejo", "lírico", "vibrar", "efluvio",
        "inefable", "etéreo", "esplendor", "resonancia", "musa",
        "clamor", "asombro",
    ),
    Language.PT: (
        "saudade", "efêmero", "passear", "crepúsculo", "sussurro",
        "luminoso", "ternura", "silêncio", "sereno", "brilhar",
        "vagar", "doçura", "riacho", "sonhar", "brisa",
        "fulgor", "clareira", "calma", "anseio", "encanto",
        "arcano", "abismo", "onírico", "labirinto", "palpitar",
        "resplendor", "quimera", "miragem", "diáfano", "cintilar",
        "rebrilhar", "rumor", "murmúrio", "embriagar", "crepuscular",
        "fosforescente", "iridescente", "olvido", "solidão", "quintessência",
        "evanescente", "reminiscência", "ressaca", "misterioso", "prelúdio",
        "telúrico", "encantado", "sibilino", "halo", "espiral",
        "subjugar", "indolência", "arabesco", "centelha", "perene",
        "cristalino", "límpido", "exuberante", "desenvolto", "púrpura",
        "vespertino", "crepitar", "cinzelar", "vertigem", "burburinho",
        "júbilo", "fugaz", "plenitude", "estremecer", "saltimbanco",
        "pirilampo", "alvorada", "orvalho", "nácar", "carícia",
        "emoção", "silhueta", "espuma", "geada", "pétala",
        "horizonte", "esteira", "lampejo", "sombra", "sopro",
        "zênite", "barroco", "berço", "matiz", "incenso",
        "joia", "ninho", "anelo", "vigília", "canto",
        "raio", "reflexo", "lírico", "vibrar", "éter",
        "inefável", "etéreo", "esplendor", "ressonância", "musa",
        "clamor", "assombro", "lume", "vestígio",
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


# Hand-authored quote fallback — used only if quotes_data.json is missing
# or unparseable. Keeps the home view alive with something reasonable.
_FALLBACK_QUOTES: dict[Language, tuple[DailyQuote, ...]] = {
    Language.FR: (
        DailyQuote("On ne voit bien qu'avec le cœur. L'essentiel est invisible pour les yeux.", "Antoine de Saint-Exupéry"),
        DailyQuote("Je pense, donc je suis.", "René Descartes"),
        DailyQuote("L'enfer, c'est les autres.", "Jean-Paul Sartre"),
    ),
    Language.EN: (
        DailyQuote("To be, or not to be, that is the question.", "William Shakespeare"),
        DailyQuote("Not all those who wander are lost.", "J.R.R. Tolkien"),
        DailyQuote("The journey of a thousand miles begins with a single step.", "Lao Tzu"),
    ),
    Language.IT: (
        DailyQuote("Nel mezzo del cammin di nostra vita mi ritrovai per una selva oscura.", "Dante Alighieri"),
        DailyQuote("L'amor che move il sole e l'altre stelle.", "Dante Alighieri"),
        DailyQuote("La semplicità è la sofisticazione suprema.", "Leonardo da Vinci"),
    ),
    Language.ES: (
        DailyQuote("En un lugar de la Mancha, de cuyo nombre no quiero acordarme…", "Miguel de Cervantes"),
        DailyQuote("Caminante, no hay camino, se hace camino al andar.", "Antonio Machado"),
        DailyQuote("La vida es sueño, y los sueños, sueños son.", "Pedro Calderón de la Barca"),
    ),
    Language.PT: (
        DailyQuote("Tudo vale a pena se a alma não é pequena.", "Fernando Pessoa"),
        DailyQuote("Navegar é preciso, viver não é preciso.", "Fernando Pessoa"),
        DailyQuote("Tudo no mundo começou com um sim.", "Clarice Lispector"),
    ),
}


_QUOTES_JSON_PATH = Path(__file__).with_name("quotes_data.json")


def _load_quote_pools() -> dict[Language, tuple[DailyQuote, ...]]:
    """Load quotes from the JSON snapshot, falling back to hand-authored data."""
    if not _QUOTES_JSON_PATH.exists():
        return dict(_FALLBACK_QUOTES)
    try:
        payload = json.loads(_QUOTES_JSON_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(_FALLBACK_QUOTES)

    raw = payload.get("languages", {})
    out: dict[Language, tuple[DailyQuote, ...]] = {}
    for lang in Language:
        items = raw.get(lang.value) or []
        pool = tuple(
            DailyQuote(text=item["text"], author=item["author"])
            for item in items
            if item.get("text") and item.get("author")
        )
        if not pool:
            pool = _FALLBACK_QUOTES.get(lang, ())
        out[lang] = pool
    return out


QUOTE_POOLS: dict[Language, tuple[DailyQuote, ...]] = _load_quote_pools()


def all_quotes(language: Language) -> tuple[DailyQuote, ...]:
    """Full pool of quotes for the given language (for browse/author-guess)."""
    return QUOTE_POOLS.get(language, ())


def quote_id(language: Language, text: str) -> str:
    """Stable identifier for a quote — used as the liked_quotes primary key."""
    return f"{language.value}::{text}"


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
