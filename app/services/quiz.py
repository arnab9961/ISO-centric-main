from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Optional

from app.core.config import DEEPSEEK_MODEL_PRO
from app.core.prompts import (
    FLASHCARD_GENERATION_SYSTEM_PROMPT,
    QUIZ_FEEDBACK_SYSTEM_PROMPT,
    QUIZ_GENERATION_SYSTEM_PROMPT,
    FOLLOWUP_QUESTION_SYSTEM_PROMPT,
)
from app.core.token_utils import is_truncated, get_json_wrap_message
from app.services.deepseek import analyze_with_deepseek, analyze_stream_with_deepseek

# ---------------------------------------------------------------------------
# In-memory question history
# ---------------------------------------------------------------------------
# Keyed by a hash of (context + iso_standard).  Stores up to MAX_HISTORY
# question strings per key so the LLM is told explicitly to avoid them.
MAX_HISTORY = 30
MAX_QUIZ_QUESTIONS = 30
MAX_FLASHCARDS = 30
MAX_AVOID_QUESTIONS_IN_PROMPT = 12
MAX_AVOID_QUESTION_CHARS = 160
MAX_PROMPT_CONTEXT_CHARS = 8000

_question_history: Dict[str, Deque[str]] = defaultdict(lambda: deque(maxlen=MAX_HISTORY))


def _context_key(context: Dict[str, Any], iso_standard: Optional[str]) -> str:
    """Stable hash that identifies a particular context+standard combination."""
    raw = json.dumps({"ctx": context, "std": iso_standard}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _record_questions(key: str, questions: list[Dict[str, Any]]) -> None:
    """Persist the question texts from a completed quiz into the history."""
    for q in questions:
        text = q.get("question", "").strip()
        if text:
            _question_history[key].append(text)


def _trim_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}..."


def _compact_context_for_prompt(context: Dict[str, Any]) -> str:
    serialized = json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    if len(serialized) <= MAX_PROMPT_CONTEXT_CHARS:
        return serialized
    return f"{serialized[:MAX_PROMPT_CONTEXT_CHARS]}...[TRUNCATED]"


def _normalize_difficulty(difficulty: str) -> str:
    value = (difficulty or "intermediate").strip().lower()
    return value if value in {"easy", "intermediate", "hard"} else "intermediate"

QUIZ_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "quiz_title": {"type": "string"},
        "iso_standard": {"type": ["string", "null"]},
        "total_questions": {"type": "integer"},
        "difficulty": {"type": "string"},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {
                        "type": "object",
                        "properties": {
                            "A": {"type": "string"},
                            "B": {"type": "string"},
                            "C": {"type": "string"},
                            "D": {"type": "string"},
                        },
                        "required": ["A", "B", "C", "D"],
                    },
                    "correct_answer": {"type": "string", "enum": ["A", "B", "C", "D"]},
                    "hint": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": ["question", "options", "correct_answer", "hint", "explanation"],
            },
        },
        "generated_at": {"type": "string"},
    },
    "required": ["quiz_title", "questions", "total_questions", "difficulty"],
}

FLASHCARD_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "deck_title": {"type": "string"},
        "iso_standard": {"type": ["string", "null"]},
        "total_cards": {"type": "integer"},
        "difficulty": {"type": "string"},
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "front": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "body": {"type": "string"},
                        },
                        "required": ["title", "body"],
                    },
                    "back": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "body": {"type": "string"},
                        },
                        "required": ["title", "body"],
                    },
                },
                "required": ["front", "back"],
            },
        },
        "generated_at": {"type": "string"},
    },
    "required": ["deck_title", "cards", "total_cards", "difficulty"],
}


async def generate_quiz(
    context: Dict[str, Any],
    num_questions: int = 5,
    iso_standard: Optional[str] = None,
    difficulty: str = "intermediate",
) -> Dict[str, Any]:
    """Generate a multiple-choice quiz from the provided context JSON. This context can be module names, in which subject you have to generate quiz for the ISO learners.

    Previously seen questions (up to the last MAX_HISTORY) are injected into
    the prompt so the model actively avoids repeating them.
    """
    num_questions = max(1, min(num_questions, MAX_QUIZ_QUESTIONS))
    difficulty = _normalize_difficulty(difficulty)

    key = _context_key(context, iso_standard)
    seen = list(_question_history[key])[-MAX_AVOID_QUESTIONS_IN_PROMPT:]
    context_payload = _compact_context_for_prompt(context)

    standard_line = f"ISO Standard: {iso_standard}\n" if iso_standard else ""
    avoid_block = ""
    if seen:
        formatted = "\n".join(
            f"  {i + 1}. {_trim_text(q, MAX_AVOID_QUESTION_CHARS)}" for i, q in enumerate(seen)
        )
        avoid_block = (
            "\n\nIMPORTANT — The following questions have ALREADY been asked. "
            "Do NOT repeat or closely paraphrase any of them:\n"
            f"{formatted}\n"
        )

    prompt = (
        f"{standard_line}"
        f"Difficulty: {difficulty}\n"
        f"Number of questions: {num_questions}\n"
        "Return exactly the requested number of questions.\n\n"
        f"Target ISO Knowledge Area (Topic Anchor):\n{context_payload}\n"
        f"{avoid_block}"
        "Constraints:\n"
        "1. Ask only advanced ISO clause-application questions.\n"
        "2. Never ask generic or meta questions about the provided JSON/context.\n"
        "3. Keep each option concise but technically plausible.\n"
        "4. Output must be valid JSON matching the required schema exactly."
    )

    # Budget tuned for short-format MCQs while supporting up to 30 questions.
    max_tokens = 8192  # Give it the maximum output tokens the API allows to prevent cutoff
    result, finish_reason = await analyze_with_deepseek(
        prompt=prompt,
        system_instruction=QUIZ_GENERATION_SYSTEM_PROMPT,
        response_schema=QUIZ_RESPONSE_SCHEMA,
        model=DEEPSEEK_MODEL_PRO,
        max_tokens=max_tokens,
    )

    # Ensure generated_at is always present
    result.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
    result.setdefault("iso_standard", iso_standard)
    result.setdefault("difficulty", difficulty)
    result.setdefault("total_questions", len(result.get("questions", [])))
    
    # Mark if response was truncated
    if is_truncated(finish_reason):
        result["_was_truncated"] = True
        result["_truncation_warning"] = get_json_wrap_message()

    # Record the newly generated questions so future calls can avoid them
    _record_questions(key, result.get("questions", []))

    return result


async def generate_flashcards(
    context: Dict[str, Any],
    num_cards: int = 8,
    iso_standard: Optional[str] = None,
    difficulty: str = "intermediate",
) -> Dict[str, Any]:
    num_cards = max(1, min(num_cards, MAX_FLASHCARDS))
    difficulty = _normalize_difficulty(difficulty)
    context_payload = _compact_context_for_prompt(context)

    standard_line = f"ISO Standard: {iso_standard}\n" if iso_standard else ""
    prompt = (
        f"{standard_line}"
        f"Difficulty: {difficulty}\n"
        f"Number of cards: {num_cards}\n"
        "Return exactly the requested number of cards.\n\n"
        f"Target ISO Knowledge Area (Topic Anchor):\n{context_payload}\n"
        "Constraints:\n"
        "1. Ensure each card teaches one focused concept.\n"
        "2. Keep the front succinct and the back authoritative.\n"
        "3. Output must be valid JSON matching the required schema exactly."
    )

    max_tokens = 8192
    result, finish_reason = await analyze_with_deepseek(
        prompt=prompt,
        system_instruction=FLASHCARD_GENERATION_SYSTEM_PROMPT,
        response_schema=FLASHCARD_RESPONSE_SCHEMA,
        model=DEEPSEEK_MODEL_PRO,
        max_tokens=max_tokens,
    )

    result.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
    result.setdefault("iso_standard", iso_standard)
    result.setdefault("difficulty", difficulty)
    result.setdefault("total_cards", len(result.get("cards", [])))
    
    # Mark if response was truncated
    if is_truncated(finish_reason):
        result["_was_truncated"] = True
        result["_truncation_warning"] = get_json_wrap_message()

    return result


async def generate_quiz_stream(
    context: Dict[str, Any],
    num_questions: int = 5,
    iso_standard: Optional[str] = None,
    difficulty: str = "intermediate",
):
    """Produces a stream of partial JSON text as the LLM generates the quiz."""
    num_questions = max(1, min(num_questions, MAX_QUIZ_QUESTIONS))
    difficulty = _normalize_difficulty(difficulty)

    key = _context_key(context, iso_standard)
    seen = list(_question_history[key])[-MAX_AVOID_QUESTIONS_IN_PROMPT:]
    context_payload = _compact_context_for_prompt(context)

    standard_line = f"ISO Standard: {iso_standard}\n" if iso_standard else ""
    avoid_block = ""
    if seen:
        formatted = "\n".join(
            f"  {i + 1}. {_trim_text(q, MAX_AVOID_QUESTION_CHARS)}" for i, q in enumerate(seen)
        )
        avoid_block = (
            "\n\nIMPORTANT — The following questions have ALREADY been asked. "
            "Do NOT repeat or closely paraphrase any of them:\n"
            f"{formatted}\n"
        )

    prompt = (
        f"{standard_line}"
        f"Difficulty: {difficulty}\n"
        f"Number of questions: {num_questions}\n"
        "Return exactly the requested number of questions.\n\n"
        f"Target ISO Knowledge Area (Topic Anchor):\n{context_payload}\n"
        f"{avoid_block}"
        "Constraints:\n"
        "1. Ask only advanced ISO clause-application questions.\n"
        "2. Never ask generic or meta questions about the provided JSON/context.\n"
        "3. Keep each option concise but technically plausible.\n"
        "4. Output must be valid JSON matching the required schema exactly."
    )

    max_tokens = 8192  # Streaming also needs maximum allowance to prevent cutoff

    # We yield chunks back. Question caching cannot easily happen on partial chunks here
    # without implementing a partial-JSON parser. It could be left to the complete response sync route,
    # or implemented via a frontend callback if needed. For now, streaming bypasses local caching.
    async for chunk in analyze_stream_with_deepseek(
        prompt=prompt,
        system_instruction=QUIZ_GENERATION_SYSTEM_PROMPT,
        response_schema=QUIZ_RESPONSE_SCHEMA,
        model=DEEPSEEK_MODEL_PRO,
        max_tokens=max_tokens,
    ):
        # Check if this is the finish_reason marker
        if isinstance(chunk, str) and chunk.startswith("__FINISH_REASON__"):
            finish_reason = chunk.replace("__FINISH_REASON__", "")
            if is_truncated(finish_reason):
                # Append wrap-up message to indicate truncation
                wrap_msg = '\n\n"_was_truncated": true, "_truncation_warning": "' + get_json_wrap_message() + '"}'
                yield wrap_msg
        else:
            yield chunk

QUIZ_FEEDBACK_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "overall_score": {"type": "string"},
        "competency_level": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "title": {"type": "string"},
                "summary": {"type": "string"},
            },
            "required": ["code", "title", "summary"],
        },
        "analytical_feedback": {
            "type": "object",
            "properties": {
                "strengths": {"type": "array", "items": {"type": "string"}},
                "weaknesses": {"type": "array", "items": {"type": "string"}},
                "critical_focus_clauses": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["strengths", "weaknesses", "critical_focus_clauses"],
        },
        "risk_assessment": {
            "type": "object",
            "properties": {
                "risk_level": {"type": "string", "enum": ["Low", "Medium", "High", "Critical"]},
                "impact_description": {"type": "string"},
                "mitigation_recommendation": {"type": "string"},
            },
            "required": ["risk_level", "impact_description", "mitigation_recommendation"],
        },
        "learning_roadmap": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "area": {"type": "string"},
                    "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
                    "resources": {"type": "array", "items": {"type": "string"}},
                    "action_item": {"type": "string"},
                },
                "required": ["area", "priority", "resources", "action_item"],
            },
        },
        "mentor_closing_note": {"type": "string"},
    },
    "required": [
        "overall_score",
        "competency_level",
        "analytical_feedback",
        "risk_assessment",
        "learning_roadmap",
        "mentor_closing_note",
    ],
}


async def generate_quiz_feedback(
    context: Dict[str, Any],
    results: list[Dict[str, Any]],
) -> Dict[str, Any]:
    """Generate detailed professional feedback based on quiz performance."""
    
    # Calculate simple score for the prompt context
    correct_count = sum(1 for r in results if r.get("selected_answer") == r.get("correct_answer"))
    total_count = len(results)
    score_pct = (correct_count / total_count * 100) if total_count > 0 else 0
    
    prompt = (
        f"Score: {score_pct:.1f}% ({correct_count}/{total_count})\n\n"
        f"Context of the Quiz:\n{json.dumps(context, indent=2)}\n\n"
        f"User Results:\n{json.dumps(results, indent=2)}\n\n"
        "Please provide a deep-dive analysis of these results. Focus on identifying patterns in the errors "
        "and correlating them to specific ISO clause weaknesses."
    )

    result, finish_reason = await analyze_with_deepseek(
        prompt=prompt,
        system_instruction=QUIZ_FEEDBACK_SYSTEM_PROMPT,
        response_schema=QUIZ_FEEDBACK_RESPONSE_SCHEMA,
        model=DEEPSEEK_MODEL_PRO,
        max_tokens=4096,
    )
    
    # Add truncation warning to feedback if needed
    if is_truncated(finish_reason):
        result["_was_truncated"] = True
        if "mentor_closing_note" in result:
            result["mentor_closing_note"] += " [Note: Feedback was truncated due to length limits.]"

    return result


FOLLOWUP_QUESTION_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {"type": "string"}
        },
        "generated_at": {"type": "string"},
    },
    "required": ["questions"],
}


async def generate_followup_question(
    context: Dict[str, Any],
    num_questions: int = 1,
) -> Dict[str, Any]:
    """Generate small related followup questions based on the context."""
    
    context_payload = _compact_context_for_prompt(context)
    
    prompt = (
        f"Context for the follow-up questions:\n{context_payload}\n\n"
        f"Please provide exactly {num_questions} small, thought-provoking follow-up question(s)."
    )

    result, finish_reason = await analyze_with_deepseek(
        prompt=prompt,
        system_instruction=FOLLOWUP_QUESTION_SYSTEM_PROMPT,
        response_schema=FOLLOWUP_QUESTION_RESPONSE_SCHEMA,
        model=DEEPSEEK_MODEL_PRO,
        max_tokens=500,
    )
    
    result.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
    
    if is_truncated(finish_reason):
        result["_was_truncated"] = True

    return result
