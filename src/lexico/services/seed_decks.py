"""Themed seed decks: hand-curated lemma lists hydrated at clone time.

Each YAML file under `lexico/data/themed_decks/` describes one deck.
Cloning a seed deck creates a new Deck in the store and looks up every
lemma via LookupService, adding a Card for each entry that succeeds.
Failed lookups are skipped silently — the user still gets a usable deck
with whatever vocabulary could be found.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

from lexico.domain.deck import Card, Deck
from lexico.domain.enums import Language
from lexico.providers.base import LookupError
from lexico.services.deck_store import DeckStore
from lexico.services.lookup_service import LookupService

logger = logging.getLogger(__name__)


_THEMED_DIR = Path(__file__).resolve().parent.parent / "data" / "themed_decks"


@dataclass(frozen=True)
class SeedDeck:
    slug: str
    name: str
    source_lang: Language
    description: str
    lemmas: tuple[str, ...]


def list_seed_decks(directory: Path | None = None) -> list[SeedDeck]:
    """Load every .yaml file in the themed decks directory."""
    directory = directory or _THEMED_DIR
    if not directory.exists():
        return []
    decks: list[SeedDeck] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            decks.append(_load_one(path))
        except Exception as exc:
            logger.warning("Skipping seed deck %s: %s", path.name, exc)
    return decks


def _load_one(path: Path) -> SeedDeck:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return SeedDeck(
        slug=path.stem,
        name=str(data["name"]),
        source_lang=Language(data["source_lang"]),
        description=str(data.get("description", "")),
        lemmas=tuple(str(l) for l in data.get("lemmas", [])),
    )


def clone_seed_deck(
    seed: SeedDeck,
    store: DeckStore,
    lookup: LookupService,
    user_id: str = "local",
) -> tuple[Deck, int, int]:
    """Create a new user deck and populate it from the seed.

    Returns `(deck, added, skipped)` so the caller can report progress.
    Card lookups are tolerant: words Wiktionary can't find are skipped.
    """
    deck = store.create_deck(
        Deck(
            user_id=user_id,
            name=seed.name,
            source_lang=seed.source_lang,
            description=seed.description,
        )
    )
    if deck.id is None:
        raise RuntimeError(f"Failed to persist seed deck {seed.slug}")

    added = 0
    skipped = 0
    for lemma in seed.lemmas:
        try:
            entry = lookup.lookup(lemma, seed.source_lang)
        except LookupError:
            skipped += 1
            continue
        store.add_card(Card.new(entry, deck_id=deck.id))
        added += 1
    return deck, added, skipped
