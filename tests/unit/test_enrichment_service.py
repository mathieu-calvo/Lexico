"""EnrichmentService tests with StubLlmProvider."""

from __future__ import annotations

import pytest

from lexico.domain.enums import Language
from lexico.providers.stub_provider import StubLlmProvider, StubDictionaryProvider
from lexico.services.enrichment_service import EnrichmentService
from lexico.services.usage_guardrail import UsageGuardrail, BudgetExceeded


@pytest.fixture
def service(tmp_path):
    guardrail = UsageGuardrail(
        tmp_path / "lexico.db",
        per_user_daily=10,
        global_daily=100,
        daily_usd_cap=10.0,
    )
    return EnrichmentService([StubLlmProvider()], guardrail)


def test_cloze_returns_sentence_and_answer(service):
    entry = StubDictionaryProvider().lookup("chat", Language.FR)
    card = service.cloze(entry)
    assert card.sentence
    assert card.answer


def test_mc_returns_three_distractors(service):
    entry = StubDictionaryProvider().lookup("chat", Language.FR)
    mc = service.multiple_choice(entry, Language.EN, "cat")
    assert len(mc.distractors) == 3
    assert mc.correct == "cat"
    assert mc.correct in mc.all_options


def test_grade_returns_result(service):
    r = service.grade_challenge(Language.FR, ["chat", "bonjour", "éphémère"], "Bonjour, mon chat est éphémère.")
    assert 0 <= r.grade <= 100


def test_tutor_returns_text(service):
    text = service.tutor("What does 'éphémère' mean?")
    assert isinstance(text, str)
    assert len(text) > 0


def test_budget_exceeded_raises(tmp_path):
    guardrail = UsageGuardrail(
        tmp_path / "lexico.db",
        per_user_daily=1,
        global_daily=100,
        daily_usd_cap=10.0,
    )
    svc = EnrichmentService([StubLlmProvider()], guardrail)
    entry = StubDictionaryProvider().lookup("chat", Language.FR)
    svc.cloze(entry)
    with pytest.raises(BudgetExceeded):
        svc.cloze(entry)


def test_is_available_true_with_stub(service):
    assert service.is_available() is True
