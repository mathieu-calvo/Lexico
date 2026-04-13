"""Deterministic offline provider with canned data for tests and zero-setup dev.

Intentionally hand-authored: 5 words per language with full translations between
all language pairs. Enough to exercise lookup, save, review, cloze, MC, stats
end-to-end without any network or keys.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date

from lexico.domain.enums import CEFRLevel, Language, PartOfSpeech
from lexico.domain.word import Example, Sense, WordEntry
from lexico.providers.base import (
    DictionaryProvider,
    LlmProvider,
    LlmResponse,
    LlmUsage,
    LookupError,
)


def _w(
    lemma: str,
    lang: Language,
    gloss: str,
    pos: PartOfSpeech,
    ipa: str,
    translations: dict[Language, str],
    example: str,
    example_tr: str,
    etymology: str,
    cefr: CEFRLevel,
) -> WordEntry:
    return WordEntry(
        lemma=lemma,
        language=lang,
        ipa=ipa,
        senses=(
            Sense(
                gloss=gloss,
                part_of_speech=pos,
                examples=(Example(text=example, translation=example_tr),),
            ),
        ),
        translations={k: (v,) for k, v in translations.items()},
        etymology=etymology,
        cefr_level=cefr,
        source="stub",
    )


_STUB_ENTRIES: list[WordEntry] = [
    # French — definitions and etymology in French
    _w("éphémère", Language.FR, "Qui ne dure qu'un temps très court ; passager, fugace.", PartOfSpeech.ADJECTIVE,
       "/e.fe.mɛʁ/",
       {Language.EN: "ephemeral", Language.IT: "effimero", Language.ES: "efímero", Language.PT: "efêmero"},
       "Le bonheur est parfois éphémère.", "Happiness is sometimes fleeting.",
       "Du grec ancien ἐφήμερος (ephēmeros), « qui ne dure qu'un jour ».", CEFRLevel.C1),
    _w("chat", Language.FR, "Petit mammifère carnivore domestique de la famille des félidés, élevé comme animal de compagnie.", PartOfSpeech.NOUN,
       "/ʃa/",
       {Language.EN: "cat", Language.IT: "gatto", Language.ES: "gato", Language.PT: "gato"},
       "Le chat dort sur le canapé.", "The cat is sleeping on the couch.",
       "Du latin tardif cattus, d'origine incertaine, probablement africaine.", CEFRLevel.A1),
    _w("flâner", Language.FR, "Se promener sans but précis, au gré de sa fantaisie, en prenant son temps.", PartOfSpeech.VERB,
       "/flɑ.ne/",
       {Language.EN: "to stroll", Language.IT: "gironzolare", Language.ES: "pasear", Language.PT: "passear"},
       "J'aime flâner dans les ruelles du vieux Paris.", "I love strolling through the old alleys of Paris.",
       "Du vieux norrois flana, « errer d'un endroit à l'autre ».", CEFRLevel.B2),
    _w("bonjour", Language.FR, "Formule de salutation employée quand on rencontre quelqu'un dans la journée.", PartOfSpeech.INTERJECTION,
       "/bɔ̃.ʒuʁ/",
       {Language.EN: "hello", Language.IT: "buongiorno", Language.ES: "hola", Language.PT: "olá"},
       "Bonjour, comment allez-vous ?", "Hello, how are you?",
       "Composé de « bon » et « jour », littéralement « bonne journée ».", CEFRLevel.A1),
    _w("liturgie", Language.FR, "Ensemble des rites et des cérémonies qui constituent le culte public d'une religion.", PartOfSpeech.NOUN,
       "/li.tyʁ.ʒi/",
       {Language.EN: "liturgy", Language.IT: "liturgia", Language.ES: "liturgia", Language.PT: "liturgia"},
       "La liturgie dominicale commence à dix heures.", "The Sunday liturgy starts at ten.",
       "Du grec ancien λειτουργία (leitourgia), « service public ».", CEFRLevel.C2),

    # English — definitions and etymology in English
    _w("serendipity", Language.EN, "The occurrence and development of events by chance in a happy or beneficial way.", PartOfSpeech.NOUN,
       "/ˌsɛɹənˈdɪpəti/",
       {Language.FR: "sérendipité", Language.IT: "serendipità", Language.ES: "serendipia", Language.PT: "serendipidade"},
       "Meeting her was pure serendipity.", "La rencontrer était une pure sérendipité.",
       "Coined by Horace Walpole in 1754 after the Persian fairy tale 'The Three Princes of Serendip', whose heroes made fortunate discoveries by accident.", CEFRLevel.C2),
    _w("cat", Language.EN, "A small domesticated carnivorous mammal of the family Felidae, kept as a pet or for catching mice.", PartOfSpeech.NOUN,
       "/kæt/",
       {Language.FR: "chat", Language.IT: "gatto", Language.ES: "gato", Language.PT: "gato"},
       "The cat is on the mat.", "Le chat est sur le tapis.",
       "From Old English catt, from Late Latin cattus, of uncertain origin, probably African.", CEFRLevel.A1),
    _w("stroll", Language.EN, "To walk in a leisurely way, often for pleasure rather than with a destination in mind.", PartOfSpeech.VERB,
       "/stroʊl/",
       {Language.FR: "flâner", Language.IT: "passeggiare", Language.ES: "pasear", Language.PT: "passear"},
       "They strolled through the park at dusk.", "Ils ont flâné dans le parc au crépuscule.",
       "Early 17th century, origin uncertain, probably from the German dialect word strollen 'to wander'.", CEFRLevel.B1),
    _w("ephemeral", Language.EN, "Lasting for a very short time; transitory.", PartOfSpeech.ADJECTIVE,
       "/ɪˈfɛmərəl/",
       {Language.FR: "éphémère", Language.IT: "effimero", Language.ES: "efímero", Language.PT: "efêmero"},
       "Fame is often ephemeral.", "La célébrité est souvent éphémère.",
       "From Ancient Greek ephēmeros, meaning 'lasting only a day'.", CEFRLevel.C1),
    _w("hello", Language.EN, "Used as a greeting or to begin a conversation.", PartOfSpeech.INTERJECTION,
       "/həˈloʊ/",
       {Language.FR: "bonjour", Language.IT: "ciao", Language.ES: "hola", Language.PT: "olá"},
       "Hello, how are you doing?", "Bonjour, comment vas-tu ?",
       "Variant of earlier 'hallo', itself an alteration of 'holla', a shout used to attract attention.", CEFRLevel.A1),

    # Italian — definitions and etymology in Italian
    _w("effimero", Language.IT, "Che dura pochissimo tempo; passeggero, fugace.", PartOfSpeech.ADJECTIVE,
       "/efˈfimero/",
       {Language.FR: "éphémère", Language.EN: "ephemeral", Language.ES: "efímero", Language.PT: "efêmero"},
       "Il successo può essere effimero.", "Success can be ephemeral.",
       "Dal greco antico ἐφήμερος (ephḗmeros), « che dura un solo giorno ».", CEFRLevel.C1),
    _w("gatto", Language.IT, "Piccolo mammifero carnivoro domestico della famiglia dei felidi.", PartOfSpeech.NOUN,
       "/ˈɡatto/",
       {Language.FR: "chat", Language.EN: "cat", Language.ES: "gato", Language.PT: "gato"},
       "Il gatto dorme sul divano.", "The cat sleeps on the sofa.",
       "Dal latino tardo cattus, di origine incerta, probabilmente africana.", CEFRLevel.A1),
    _w("passeggiare", Language.IT, "Camminare tranquillamente per svago, senza una meta precisa.", PartOfSpeech.VERB,
       "/passedˈdʒare/",
       {Language.FR: "se promener", Language.EN: "to stroll", Language.ES: "pasear", Language.PT: "passear"},
       "Mi piace passeggiare dopo cena.", "I like to stroll after dinner.",
       "Derivato di « passo », dal latino passus.", CEFRLevel.A2),
    _w("ciao", Language.IT, "Saluto confidenziale usato sia incontrandosi sia congedandosi.", PartOfSpeech.INTERJECTION,
       "/tʃao/",
       {Language.FR: "salut", Language.EN: "hi", Language.ES: "hola", Language.PT: "oi"},
       "Ciao, come stai?", "Hi, how are you?",
       "Dal veneto « s-ciào vostro », letteralmente « (sono) vostro schiavo », antica formula di cortesia.", CEFRLevel.A1),
    _w("meraviglia", Language.IT, "Sentimento di stupore e ammirazione provocato da qualcosa di straordinario.", PartOfSpeech.NOUN,
       "/meraˈviʎʎa/",
       {Language.FR: "merveille", Language.EN: "wonder", Language.ES: "maravilla", Language.PT: "maravilha"},
       "Che meraviglia questo panorama!", "What a marvel this view is!",
       "Dal latino mirabilia, « cose meravigliose », plurale di mirabilis.", CEFRLevel.B1),

    # Spanish — definitions and etymology in Spanish
    _w("efímero", Language.ES, "Que dura muy poco tiempo; pasajero, fugaz.", PartOfSpeech.ADJECTIVE,
       "/eˈfimeɾo/",
       {Language.FR: "éphémère", Language.EN: "ephemeral", Language.IT: "effimero", Language.PT: "efêmero"},
       "La belleza es efímera.", "Beauty is ephemeral.",
       "Del griego antiguo ἐφήμερος (ephḗmeros), « que dura un solo día ».", CEFRLevel.C1),
    _w("gato", Language.ES, "Pequeño mamífero carnívoro doméstico de la familia de los félidos.", PartOfSpeech.NOUN,
       "/ˈɡato/",
       {Language.FR: "chat", Language.EN: "cat", Language.IT: "gatto", Language.PT: "gato"},
       "El gato duerme en el sofá.", "The cat sleeps on the sofa.",
       "Del latín tardío cattus, de origen incierto, probablemente africano.", CEFRLevel.A1),
    _w("pasear", Language.ES, "Andar por distracción, sin una meta fija, normalmente al aire libre.", PartOfSpeech.VERB,
       "/paseˈaɾ/",
       {Language.FR: "se promener", Language.EN: "to stroll", Language.IT: "passeggiare", Language.PT: "passear"},
       "Vamos a pasear por el parque.", "Let's stroll through the park.",
       "Derivado de « paso », del latín passus.", CEFRLevel.A2),
    _w("hola", Language.ES, "Interjección usada como saludo familiar al encontrarse con alguien.", PartOfSpeech.INTERJECTION,
       "/ˈola/",
       {Language.FR: "bonjour", Language.EN: "hello", Language.IT: "ciao", Language.PT: "olá"},
       "¡Hola! ¿Cómo estás?", "Hello! How are you?",
       "De origen incierto, atestiguado desde el español medieval.", CEFRLevel.A1),
    _w("duende", Language.ES, "Encanto misterioso e inefable, especialmente en el arte flamenco; también, espíritu fantástico que habita una casa.", PartOfSpeech.NOUN,
       "/ˈdwende/",
       {Language.FR: "duende", Language.EN: "duende", Language.IT: "duende", Language.PT: "duende"},
       "El cantaor tenía mucho duende.", "The flamenco singer had great duende.",
       "De « dueño de casa », evolucionó hacia el sentido de « espíritu que habita la casa ».", CEFRLevel.C2),

    # Portuguese — definitions and etymology in Portuguese
    _w("saudade", Language.PT, "Sentimento profundo de falta ou de nostalgia por alguém ou algo ausente e querido.", PartOfSpeech.NOUN,
       "/sawˈdadʒi/",
       {Language.FR: "saudade", Language.EN: "longing", Language.IT: "nostalgia", Language.ES: "añoranza"},
       "Tenho saudade do Porto.", "I long for Porto.",
       "Do latim solitas, -atis, « solidão », através do português antigo soidade.", CEFRLevel.B2),
    _w("gato", Language.PT, "Pequeno mamífero carnívoro doméstico da família dos felídeos.", PartOfSpeech.NOUN,
       "/ˈɡatu/",
       {Language.FR: "chat", Language.EN: "cat", Language.IT: "gatto", Language.ES: "gato"},
       "O gato está a dormir no sofá.", "The cat is sleeping on the sofa.",
       "Do latim tardio cattus, de origem incerta, provavelmente africana.", CEFRLevel.A1),
    _w("passear", Language.PT, "Andar sem destino fixo, por distração ou prazer.", PartOfSpeech.VERB,
       "/pɐsiˈaɾ/",
       {Language.FR: "se promener", Language.EN: "to stroll", Language.IT: "passeggiare", Language.ES: "pasear"},
       "Vamos passear à beira-mar.", "Let's walk along the seaside.",
       "Derivado de « passo », do latim passus.", CEFRLevel.A2),
    _w("olá", Language.PT, "Interjeição usada como saudação familiar ao encontrar alguém.", PartOfSpeech.INTERJECTION,
       "/ɔˈla/",
       {Language.FR: "bonjour", Language.EN: "hello", Language.IT: "ciao", Language.ES: "hola"},
       "Olá, tudo bem?", "Hello, all well?",
       "Provavelmente do castelhano hola, de origem incerta.", CEFRLevel.A1),
    _w("efêmero", Language.PT, "Que dura pouquíssimo tempo; passageiro, transitório.", PartOfSpeech.ADJECTIVE,
       "/eˈfẽmeɾu/",
       {Language.FR: "éphémère", Language.EN: "ephemeral", Language.IT: "effimero", Language.ES: "efímero"},
       "O prazer foi efêmero.", "The pleasure was ephemeral.",
       "Do grego antigo ἐφήμερος (ephḗmeros), « que dura um só dia ».", CEFRLevel.C1),
]


def _index() -> dict[tuple[Language, str], WordEntry]:
    return {(e.language, e.lemma.lower()): e for e in _STUB_ENTRIES}


class StubDictionaryProvider:
    """Canned dictionary with ~5 entries per language."""

    def __init__(self) -> None:
        self._index = _index()

    @property
    def name(self) -> str:
        return "stub"

    def lookup(self, lemma: str, language: Language) -> WordEntry:
        key = (language, lemma.lower())
        if key not in self._index:
            raise LookupError(f"{lemma!r} not in stub provider for {language.value}")
        return self._index[key]

    def random_lemma(self, language: Language) -> str | None:
        candidates = [e.lemma for e in _STUB_ENTRIES if e.language == language]
        if not candidates:
            return None
        idx = date.today().toordinal() % len(candidates)
        return candidates[idx]

    def all_lemmas(self, language: Language) -> list[str]:
        return [e.lemma for e in _STUB_ENTRIES if e.language == language]


# Verify the protocol is satisfied at import time.
_: DictionaryProvider = StubDictionaryProvider()


class StubLlmProvider:
    """Deterministic LLM stand-in.

    Returns canned cloze / MC / chat text so the UI can be exercised offline.
    Output is a function of the input so tests are reproducible.
    """

    @property
    def name(self) -> str:
        return "stub"

    @property
    def is_available(self) -> bool:
        return True

    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 512,
        json_mode: bool = False,
    ) -> LlmResponse:
        seed = int(hashlib.md5((system + "||" + user).encode("utf-8")).hexdigest(), 16)
        rng = random.Random(seed)

        if json_mode:
            text = (
                '{"sentence": "This is a stub cloze sentence about ___.", '
                '"answer": "the word", '
                '"distractors": ["alpha", "beta", "gamma"], '
                '"grade": ' + str(rng.randint(60, 100)) + ', '
                '"feedback": "Stub feedback: looks good!"}'
            )
        else:
            text = (
                "Stub LLM response. This is a deterministic placeholder so "
                "the UI can exercise LLM features without a real API key. "
                f"(seed={seed % 10000})"
            )

        return LlmResponse(
            text=text,
            usage=LlmUsage(
                provider="stub",
                model="stub-1",
                tokens_in=len(user) // 4,
                tokens_out=len(text) // 4,
                usd=0.0,
            ),
        )


_: LlmProvider = StubLlmProvider()
