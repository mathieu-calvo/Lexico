"""Deck and Card domain models."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from lexico.domain.enums import Language
from lexico.domain.review import FSRSState
from lexico.domain.word import WordEntry


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Card(BaseModel):
    """A review card owned by a deck, wrapping a WordEntry and its FSRS state."""

    model_config = ConfigDict(frozen=False)  # fsrs_state is updated on review

    id: int | None = None
    deck_id: int | None = None
    entry: WordEntry
    note: str = ""
    fsrs_state: FSRSState
    added_at: datetime = Field(default_factory=_utcnow)

    @classmethod
    def new(cls, entry: WordEntry, deck_id: int | None = None, note: str = "") -> "Card":
        now = _utcnow()
        return cls(
            deck_id=deck_id,
            entry=entry,
            note=note,
            fsrs_state=FSRSState.new(now),
            added_at=now,
        )


class Deck(BaseModel):
    model_config = ConfigDict(frozen=False)

    id: int | None = None
    user_id: str = "local"
    name: str
    source_lang: Language
    target_lang: Language
    description: str = ""
    created_at: datetime = Field(default_factory=_utcnow)

    @property
    def slug(self) -> str:
        return self.name.lower().replace(" ", "_")
