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
    # French
    _w("éphémère", Language.FR, "lasting only a short time; fleeting", PartOfSpeech.ADJECTIVE,
       "/e.fe.mɛʁ/",
       {Language.EN: "ephemeral", Language.IT: "effimero", Language.ES: "efímero", Language.PT: "efêmero"},
       "Le bonheur est parfois éphémère.", "Happiness is sometimes fleeting.",
       "From Ancient Greek ἐφήμερος 'lasting a day'.", CEFRLevel.C1),
    _w("chat", Language.FR, "cat; small domesticated feline", PartOfSpeech.NOUN,
       "/ʃa/",
       {Language.EN: "cat", Language.IT: "gatto", Language.ES: "gato", Language.PT: "gato"},
       "Le chat dort sur le canapé.", "The cat is sleeping on the couch.",
       "From Latin cattus.", CEFRLevel.A1),
    _w("flâner", Language.FR, "to stroll aimlessly; wander leisurely", PartOfSpeech.VERB,
       "/flɑ.ne/",
       {Language.EN: "to stroll", Language.IT: "gironzolare", Language.ES: "pasear", Language.PT: "passear"},
       "J'aime flâner dans les ruelles.", "I love strolling through the alleys.",
       "From Old Norse flana 'to rush about'.", CEFRLevel.B2),
    _w("bonjour", Language.FR, "hello; good day (greeting)", PartOfSpeech.INTERJECTION,
       "/bɔ̃.ʒuʁ/",
       {Language.EN: "hello", Language.IT: "buongiorno", Language.ES: "hola", Language.PT: "olá"},
       "Bonjour, comment allez-vous ?", "Hello, how are you?",
       "From bon + jour 'good day'.", CEFRLevel.A1),
    _w("liturgie", Language.FR, "a set of rituals in religious worship", PartOfSpeech.NOUN,
       "/li.tyʁ.ʒi/",
       {Language.EN: "liturgy", Language.IT: "liturgia", Language.ES: "liturgia", Language.PT: "liturgia"},
       "La liturgie dominicale commence à dix heures.", "The Sunday liturgy starts at ten.",
       "From Ancient Greek λειτουργία 'public service'.", CEFRLevel.C2),

    # English
    _w("serendipity", Language.EN, "the occurrence of happy or beneficial events by chance", PartOfSpeech.NOUN,
       "/ˌsɛɹənˈdɪpəti/",
       {Language.FR: "sérendipité", Language.IT: "serendipità", Language.ES: "serendipia", Language.PT: "serendipidade"},
       "Meeting her was pure serendipity.", "La rencontrer était une pure sérendipité.",
       "Coined by Horace Walpole in 1754 from the Persian fairy tale 'The Three Princes of Serendip'.", CEFRLevel.C2),
    _w("cat", Language.EN, "small domesticated feline", PartOfSpeech.NOUN,
       "/kæt/",
       {Language.FR: "chat", Language.IT: "gatto", Language.ES: "gato", Language.PT: "gato"},
       "The cat is on the mat.", "Le chat est sur le tapis.",
       "Old English catt, from Late Latin cattus.", CEFRLevel.A1),
    _w("stroll", Language.EN, "to walk in a leisurely way", PartOfSpeech.VERB,
       "/stroʊl/",
       {Language.FR: "flâner", Language.IT: "passeggiare", Language.ES: "pasear", Language.PT: "passear"},
       "They strolled through the park at dusk.", "Ils ont flâné dans le parc au crépuscule.",
       "Early 17th century, origin uncertain, possibly from German strollen.", CEFRLevel.B1),
    _w("ephemeral", Language.EN, "lasting for a very short time", PartOfSpeech.ADJECTIVE,
       "/ɪˈfɛmərəl/",
       {Language.FR: "éphémère", Language.IT: "effimero", Language.ES: "efímero", Language.PT: "efêmero"},
       "Fame is often ephemeral.", "La célébrité est souvent éphémère.",
       "From Greek ephēmeros 'lasting a day'.", CEFRLevel.C1),
    _w("hello", Language.EN, "used as a greeting", PartOfSpeech.INTERJECTION,
       "/həˈloʊ/",
       {Language.FR: "bonjour", Language.IT: "ciao", Language.ES: "hola", Language.PT: "olá"},
       "Hello, how are you doing?", "Bonjour, comment vas-tu ?",
       "Variant of earlier hallo, alteration of holla.", CEFRLevel.A1),

    # Italian
    _w("effimero", Language.IT, "short-lived; ephemeral", PartOfSpeech.ADJECTIVE,
       "/efˈfimero/",
       {Language.FR: "éphémère", Language.EN: "ephemeral", Language.ES: "efímero", Language.PT: "efêmero"},
       "Il successo può essere effimero.", "Success can be ephemeral.",
       "From Ancient Greek ἐφήμερος.", CEFRLevel.C1),
    _w("gatto", Language.IT, "cat", PartOfSpeech.NOUN,
       "/ˈɡatto/",
       {Language.FR: "chat", Language.EN: "cat", Language.ES: "gato", Language.PT: "gato"},
       "Il gatto dorme sul divano.", "The cat sleeps on the sofa.",
       "From Late Latin cattus.", CEFRLevel.A1),
    _w("passeggiare", Language.IT, "to stroll; go for a walk", PartOfSpeech.VERB,
       "/passedˈdʒare/",
       {Language.FR: "se promener", Language.EN: "to stroll", Language.ES: "pasear", Language.PT: "passear"},
       "Mi piace passeggiare dopo cena.", "I like to stroll after dinner.",
       "From passo 'step'.", CEFRLevel.A2),
    _w("ciao", Language.IT, "hi; bye (informal)", PartOfSpeech.INTERJECTION,
       "/tʃao/",
       {Language.FR: "salut", Language.EN: "hi", Language.ES: "hola", Language.PT: "oi"},
       "Ciao, come stai?", "Hi, how are you?",
       "From Venetian s-ciào vostro 'I am your slave', an old polite greeting.", CEFRLevel.A1),
    _w("meraviglia", Language.IT, "wonder; marvel", PartOfSpeech.NOUN,
       "/merav́iʎa/",
       {Language.FR: "merveille", Language.EN: "wonder", Language.ES: "maravilla", Language.PT: "maravilha"},
       "Che meraviglia questo panorama!", "What a marvel this view is!",
       "From Latin mirabilia 'wonderful things'.", CEFRLevel.B1),

    # Spanish
    _w("efímero", Language.ES, "short-lived; ephemeral", PartOfSpeech.ADJECTIVE,
       "/eˈfimeɾo/",
       {Language.FR: "éphémère", Language.EN: "ephemeral", Language.IT: "effimero", Language.PT: "efêmero"},
       "La belleza es efímera.", "Beauty is ephemeral.",
       "From Ancient Greek ἐφήμερος.", CEFRLevel.C1),
    _w("gato", Language.ES, "cat", PartOfSpeech.NOUN,
       "/ˈɡato/",
       {Language.FR: "chat", Language.EN: "cat", Language.IT: "gatto", Language.PT: "gato"},
       "El gato duerme en el sofá.", "The cat sleeps on the sofa.",
       "From Late Latin cattus.", CEFRLevel.A1),
    _w("pasear", Language.ES, "to stroll; take a walk", PartOfSpeech.VERB,
       "/paseˈaɾ/",
       {Language.FR: "se promener", Language.EN: "to stroll", Language.IT: "passeggiare", Language.PT: "passear"},
       "Vamos a pasear por el parque.", "Let's stroll through the park.",
       "From paso 'step'.", CEFRLevel.A2),
    _w("hola", Language.ES, "hello", PartOfSpeech.INTERJECTION,
       "/ˈola/",
       {Language.FR: "bonjour", Language.EN: "hello", Language.IT: "ciao", Language.PT: "olá"},
       "¡Hola! ¿Cómo estás?", "Hello! How are you?",
       "Attested since medieval Spanish.", CEFRLevel.A1),
    _w("duende", Language.ES, "untranslatable spirit of art; soulful magic, esp. in flamenco", PartOfSpeech.NOUN,
       "/ˈdwende/",
       {Language.FR: "duende", Language.EN: "duende", Language.IT: "duende", Language.PT: "duende"},
       "El cantaor tenía mucho duende.", "The flamenco singer had great duende.",
       "From dueño de casa 'owner of the house', later 'house spirit'.", CEFRLevel.C2),

    # Portuguese
    _w("saudade", Language.PT, "deep emotional longing for something absent", PartOfSpeech.NOUN,
       "/sawˈdadʒi/",
       {Language.FR: "saudade", Language.EN: "longing", Language.IT: "nostalgia", Language.ES: "añoranza"},
       "Tenho saudade do Porto.", "I long for Porto.",
       "From Latin solitas 'solitude', via Old Portuguese soidade.", CEFRLevel.B2),
    _w("gato", Language.PT, "cat", PartOfSpeech.NOUN,
       "/ˈɡatu/",
       {Language.FR: "chat", Language.EN: "cat", Language.IT: "gatto", Language.ES: "gato"},
       "O gato está a dormir no sofá.", "The cat is sleeping on the sofa.",
       "From Late Latin cattus.", CEFRLevel.A1),
    _w("passear", Language.PT, "to stroll; take a walk", PartOfSpeech.VERB,
       "/paseˈaɾ/",
       {Language.FR: "se promener", Language.EN: "to stroll", Language.IT: "passeggiare", Language.ES: "pasear"},
       "Vamos passear à beira-mar.", "Let's walk along the seaside.",
       "From passo 'step'.", CEFRLevel.A2),
    _w("olá", Language.PT, "hello", PartOfSpeech.INTERJECTION,
       "/oˈla/",
       {Language.FR: "bonjour", Language.EN: "hello", Language.IT: "ciao", Language.ES: "hola"},
       "Olá, tudo bem?", "Hello, all well?",
       "Borrowed from Spanish hola.", CEFRLevel.A1),
    _w("efêmero", Language.PT, "short-lived; ephemeral", PartOfSpeech.ADJECTIVE,
       "/eˈfẽmeɾu/",
       {Language.FR: "éphémère", Language.EN: "ephemeral", Language.IT: "effimero", Language.ES: "efímero"},
       "O prazer foi efêmero.", "The pleasure was ephemeral.",
       "From Ancient Greek ἐφήμερος.", CEFRLevel.C1),
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
