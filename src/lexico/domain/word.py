"""Dictionary entry models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lexico.domain.enums import CEFRLevel, Language, PartOfSpeech


class Example(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    translation: str | None = None


class Sense(BaseModel):
    model_config = ConfigDict(frozen=True)

    gloss: str
    part_of_speech: PartOfSpeech = PartOfSpeech.OTHER
    examples: tuple[Example, ...] = ()
    synonyms: tuple[str, ...] = ()
    antonyms: tuple[str, ...] = ()
    register_label: str | None = None  # formal, colloquial, slang, archaic, ...


class WordEntry(BaseModel):
    """A dictionary entry for a single lemma in a single language."""

    model_config = ConfigDict(frozen=True)

    lemma: str
    language: Language
    ipa: str | None = None
    senses: tuple[Sense, ...] = ()
    translations: dict[Language, tuple[str, ...]] = Field(default_factory=dict)
    derived: tuple[str, ...] = ()
    etymology: str | None = None
    cefr_level: CEFRLevel | None = None
    source: str = "stub"

    @property
    def cache_key(self) -> str:
        return f"{self.language.value}:{self.lemma.lower()}:{self.source}"

    def primary_translation(self, target: Language) -> str | None:
        values = self.translations.get(target)
        return values[0] if values else None
