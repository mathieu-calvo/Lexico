"""Curated daily pools: word-of-the-day, expression, and quote per language.

Lives in `data/` (not `providers/`) because these are hand-authored constants —
not looked up, fetched, or generated. The home view pulls one item per pool per
day, indexed deterministically by date so every user sees the same thing on the
same day without needing a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from lexico.domain.enums import Language


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


# Expressions — idioms / turns of phrase with a short plain-language meaning.
EXPRESSION_POOLS: dict[Language, tuple[DailyExpression, ...]] = {
    Language.FR: (
        DailyExpression("coûter les yeux de la tête", "Être extrêmement cher."),
        DailyExpression("poser un lapin", "Ne pas venir à un rendez-vous."),
        DailyExpression("avoir le cafard", "Être triste, déprimé."),
        DailyExpression("tomber dans les pommes", "S'évanouir."),
        DailyExpression("appeler un chat un chat", "Dire les choses comme elles sont."),
        DailyExpression("ne pas être dans son assiette", "Ne pas se sentir bien."),
        DailyExpression("avoir un poil dans la main", "Être paresseux."),
        DailyExpression("jeter l'éponge", "Abandonner, renoncer."),
        DailyExpression("prendre ses jambes à son cou", "S'enfuir rapidement."),
        DailyExpression("faire la grasse matinée", "Dormir tard le matin."),
    ),
    Language.EN: (
        DailyExpression("to bite the bullet", "To accept something difficult with courage."),
        DailyExpression("under the weather", "Feeling unwell."),
        DailyExpression("a piece of cake", "Something very easy."),
        DailyExpression("spill the beans", "Reveal a secret."),
        DailyExpression("hit the sack", "Go to bed."),
        DailyExpression("break the ice", "Start a conversation in an awkward moment."),
        DailyExpression("cost an arm and a leg", "Be very expensive."),
        DailyExpression("let the cat out of the bag", "Accidentally reveal a secret."),
        DailyExpression("once in a blue moon", "Very rarely."),
        DailyExpression("burn the midnight oil", "Work late into the night."),
    ),
    Language.IT: (
        DailyExpression("in bocca al lupo", "Formula per augurare buona fortuna."),
        DailyExpression("non vedo l'ora", "Non riesco ad aspettare, sono impaziente."),
        DailyExpression("avere le mani bucate", "Spendere troppi soldi, essere spendaccione."),
        DailyExpression("rompere il ghiaccio", "Iniziare una conversazione in un momento imbarazzante."),
        DailyExpression("essere al settimo cielo", "Essere felicissimo."),
        DailyExpression("prendere due piccioni con una fava", "Ottenere due risultati con un'azione sola."),
        DailyExpression("avere la testa fra le nuvole", "Essere distratto, sognatore."),
        DailyExpression("costare un occhio della testa", "Essere molto caro."),
        DailyExpression("non tutte le ciambelle riescono col buco", "Non sempre le cose vanno come previsto."),
        DailyExpression("chi dorme non piglia pesci", "Chi è pigro non ottiene risultati."),
    ),
    Language.ES: (
        DailyExpression("estar en las nubes", "Estar distraído o soñando despierto."),
        DailyExpression("tomar el pelo", "Burlarse de alguien, engañarlo en broma."),
        DailyExpression("ser pan comido", "Ser muy fácil."),
        DailyExpression("no tener pelos en la lengua", "Hablar con franqueza."),
        DailyExpression("costar un ojo de la cara", "Ser muy caro."),
        DailyExpression("meter la pata", "Cometer un error."),
        DailyExpression("estar como una cabra", "Estar loco, ser excéntrico."),
        DailyExpression("dar en el clavo", "Acertar exactamente."),
        DailyExpression("ponerse las pilas", "Espabilarse, esforzarse."),
        DailyExpression("a mal tiempo, buena cara", "Afrontar la adversidad con optimismo."),
    ),
    Language.PT: (
        DailyExpression("engolir sapos", "Tolerar coisas desagradáveis em silêncio."),
        DailyExpression("ficar de molho", "Ficar de repouso, sobretudo por doença."),
        DailyExpression("pagar o pato", "Levar a culpa por algo que não fez."),
        DailyExpression("dar com os burros n'água", "Fracassar numa tentativa."),
        DailyExpression("descascar o abacaxi", "Resolver um problema difícil."),
        DailyExpression("chutar o balde", "Perder a paciência e desistir."),
        DailyExpression("quebrar o galho", "Dar um jeito provisório para ajudar."),
        DailyExpression("custar os olhos da cara", "Ser muito caro."),
        DailyExpression("estar com a cabeça nas nuvens", "Estar distraído, sonhador."),
        DailyExpression("não ver um palmo à frente do nariz", "Não perceber o óbvio."),
    ),
}


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
