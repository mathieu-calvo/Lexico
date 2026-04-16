"""Versioned LLM prompt templates."""

from __future__ import annotations

from lexico.domain.enums import Language
from lexico.domain.word import WordEntry

PROMPT_VERSION = "2026-04-13"


CLOZE_SYSTEM = """You are a language tutor generating fill-in-the-blank cloze sentences for a spaced-repetition app.
Return strict JSON only, no prose: {"sentence": "...", "answer": "..."}
The sentence must be natural, 8-15 words, and contain exactly one blank marked "___".
The answer must be the exact form that fills the blank (respecting conjugation, agreement, etc.).
Do not use the lemma in any form other than the blanked slot."""


def cloze_user(entry: WordEntry) -> str:
    gloss = entry.senses[0].gloss if entry.senses else ""
    return (
        f"Language: {entry.language.display_name}\n"
        f"Word: {entry.lemma}\n"
        f"Meaning: {gloss}\n"
        f"Generate one cloze sentence."
    )


MC_SYSTEM = """You generate multiple-choice distractors for a vocabulary quiz.
Return strict JSON only, no prose: {"distractors": ["w1", "w2", "w3"]}
Distractors must be real words in the target language, plausible but unambiguously wrong for the prompt.
Prefer near-synonyms, false friends, and words from the same semantic field.
Never include the correct answer."""


def mc_user(entry: WordEntry, target: Language, correct: str) -> str:
    return (
        f"Prompt word: {entry.lemma} ({entry.language.display_name})\n"
        f"Target language: {target.display_name}\n"
        f"Correct answer: {correct}\n"
        f"Generate 3 distractors."
    )


GRADE_SYSTEM = """You grade a single sentence written by a language learner who was asked to use given words in one sentence.
Return strict JSON only, no prose: {"grade": 0-100, "feedback": "...", "correction": "..."}
Grade 90+ means native-level. 70-89 means understandable with minor issues. 50-69 has grammar problems. Below 50 is wrong.
Feedback: one short encouraging sentence. Correction: the sentence rewritten correctly, or empty if already correct.
Be warm, not harsh."""


def grade_user(language: Language, required_words: list[str], sentence: str) -> str:
    return (
        f"Language: {language.display_name}\n"
        f"Required words (must all be used): {', '.join(required_words)}\n"
        f"Student sentence: {sentence}"
    )


TUTOR_SYSTEM = """You are a warm, concise language tutor.
The user is studying vocabulary in a spaced-repetition app and wants to chat about a specific word
or about their recent saved words. Keep responses under 120 words unless asked for more.
Give concrete examples, explain register when relevant, and never lecture."""


QUOTE_CONTEXT_SYSTEM = """You explain the context behind a quote for a language learner.
Write in English. Be concise (120-180 words), warm, and concrete — no lecturing, no filler.
Cover what matters for this specific quote:
- For literary/historical quotes: the author, the work it comes from (book, play, speech, letter) and approximate date,
  the situation in which it was said or written, and what the author meant.
- For proverbs or idioms: where it's used, what it means, and a short example of a situation where it fits.
If you are not confident about a specific attribution or source, say so briefly rather than inventing details."""


def quote_context_user(language: Language, text: str, author: str) -> str:
    return (
        f"Language: {language.display_name}\n"
        f"Quote: \u201C{text}\u201D\n"
        f"Attributed to: {author}\n"
        f"Explain the context."
    )
