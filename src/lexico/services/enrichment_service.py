"""EnrichmentService: LLM chain for cloze, MC, grading, tutor chat."""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from typing import Sequence

from lexico.domain.enums import Language
from lexico.domain.word import WordEntry
from lexico.providers.base import LlmProvider
from lexico.services.usage_guardrail import BudgetExceeded, UsageGuardrail
from lexico.utils import prompts

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClozeCard:
    sentence: str
    answer: str


@dataclass(frozen=True)
class MultipleChoiceCard:
    prompt: str
    correct: str
    distractors: tuple[str, ...]

    @property
    def all_options(self) -> list[str]:
        options = [self.correct, *self.distractors]
        random.Random(self.prompt + self.correct).shuffle(options)
        return options


@dataclass(frozen=True)
class GradeResult:
    grade: int
    feedback: str
    correction: str


class EnrichmentService:
    """Run LLM-backed features through a provider chain + guardrail.

    The first available provider wins. If the guardrail refuses a call,
    BudgetExceeded bubbles up to the UI so it can render a friendly
    "come back tomorrow" message without breaking the rest of the app.
    """

    def __init__(
        self,
        providers: Sequence[LlmProvider],
        guardrail: UsageGuardrail,
    ) -> None:
        if not providers:
            raise ValueError("EnrichmentService needs at least one LlmProvider")
        self._providers = list(providers)
        self._guardrail = guardrail

    def _pick(self) -> LlmProvider:
        for p in self._providers:
            if p.is_available:
                return p
        raise RuntimeError("No available LLM provider")

    def _call(
        self,
        user_id: str,
        system: str,
        user: str,
        json_mode: bool,
        max_tokens: int = 512,
    ) -> str:
        self._guardrail.allow(user_id)
        provider = self._pick()
        response = provider.complete(system, user, max_tokens=max_tokens, json_mode=json_mode)
        self._guardrail.record(
            user_id=user_id,
            provider=response.usage.provider,
            model=response.usage.model,
            tokens_in=response.usage.tokens_in,
            tokens_out=response.usage.tokens_out,
            usd=response.usage.usd,
        )
        return response.text

    def cloze(self, entry: WordEntry, user_id: str = "local") -> ClozeCard:
        raw = self._call(
            user_id,
            prompts.CLOZE_SYSTEM,
            prompts.cloze_user(entry),
            json_mode=True,
        )
        data = _parse_json(raw)
        return ClozeCard(
            sentence=data.get("sentence", "___"),
            answer=data.get("answer", entry.lemma),
        )

    def multiple_choice(
        self,
        entry: WordEntry,
        target: Language,
        correct: str,
        user_id: str = "local",
    ) -> MultipleChoiceCard:
        raw = self._call(
            user_id,
            prompts.MC_SYSTEM,
            prompts.mc_user(entry, target, correct),
            json_mode=True,
        )
        data = _parse_json(raw)
        distractors = tuple(data.get("distractors", ["?", "?", "?"])[:3])
        return MultipleChoiceCard(
            prompt=entry.lemma,
            correct=correct,
            distractors=distractors,
        )

    def grade_challenge(
        self,
        language: Language,
        required_words: list[str],
        sentence: str,
        user_id: str = "local",
    ) -> GradeResult:
        raw = self._call(
            user_id,
            prompts.GRADE_SYSTEM,
            prompts.grade_user(language, required_words, sentence),
            json_mode=True,
            max_tokens=300,
        )
        data = _parse_json(raw)
        return GradeResult(
            grade=int(data.get("grade", 0)),
            feedback=data.get("feedback", ""),
            correction=data.get("correction", ""),
        )

    def quote_context(
        self, language: Language, text: str, author: str, user_id: str = "local"
    ) -> str:
        return self._call(
            user_id,
            prompts.QUOTE_CONTEXT_SYSTEM,
            prompts.quote_context_user(language, text, author),
            json_mode=False,
            max_tokens=400,
        )

    def tutor(self, question: str, context: str = "", user_id: str = "local") -> str:
        user = f"{context}\n\nUser: {question}" if context else question
        return self._call(
            user_id,
            prompts.TUTOR_SYSTEM,
            user,
            json_mode=False,
            max_tokens=400,
        )

    def is_available(self) -> bool:
        try:
            self._pick()
            return True
        except RuntimeError:
            return False

    def is_real_llm_available(self) -> bool:
        """True iff an available provider is backed by a real API (not stub).

        The home/challenge/tutor views use this to decide whether to show a
        "no real LLM configured" banner — a stub provider technically satisfies
        `is_available`, but its canned responses don't actually grade or tutor.
        """
        for p in self._providers:
            if getattr(p, "name", None) == "stub":
                continue
            if p.is_available:
                return True
        return False


def _parse_json(raw: str) -> dict:
    """Tolerant JSON extraction — strips markdown fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    logger.warning("Failed to parse JSON from LLM: %s", raw[:200])
    return {}
