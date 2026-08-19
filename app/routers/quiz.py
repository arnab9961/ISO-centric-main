import asyncio
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.core.models import (
    FlashcardResponse,
    QuizFeedbackRequest,
    QuizFeedbackResponse,
    QuizResponse,
    FollowupQuestionRequest,
    FollowupQuestionResponse,
)
from app.services.benchmark import extract_text_from_file
from app.services.quiz import (
    generate_flashcards,
    generate_quiz,
    generate_quiz_feedback,
    generate_quiz_stream,
    generate_followup_question,
)

router = APIRouter(prefix="/api/v1/quiz", tags=["Quiz Generator"])
logger = logging.getLogger(__name__)


def _parse_context(raw_context: str) -> dict:
    if not raw_context or not raw_context.strip():
        return {}
    try:
        parsed = json.loads(raw_context)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON in context") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="context must be a JSON object")
    return parsed


async def _extract_uploaded_file(file: UploadFile) -> dict:
    content = await file.read()
    try:
        file_text = await extract_text_from_file(file, content)
    except Exception as exc:
        logger.warning("File extraction failed in /api/v1/quiz for file '%s': %s", file.filename, exc)
        raise HTTPException(status_code=400, detail=f"Failed to process file {file.filename}: {str(exc)}") from exc
    return {
        "file_name": file.filename,
        "file_text": file_text,
    }


@router.post("/generate", response_model=QuizResponse)
async def generate_quiz_endpoint(
    context: str = Form("{}", description="JSON string of context data"),
    num_questions: int = Form(5, ge=1, le=30, description="How many questions to generate (1-30)"),
    difficulty: str = Form("intermediate", description="easy, intermediate, or hard"),
    file: Optional[UploadFile] = File(default=None),
):
    """
    Quiz Generator — create a multiple-choice quiz from any JSON context.

    **Input:**
    - `context` *(optional)*: JSON string describing the topic, subject matter,
      or structured content the quiz should be based on.
    - `num_questions`: How many questions to generate (1–30, default 5).
    - `difficulty`: `"easy"`, `"intermediate"`, or `"hard"` (default: `"intermediate"`).
    - `file`: Optional file upload to generate the quiz from.

    **Output:**
    - A `quiz_title` and list of questions, each containing:
      - The question text
      - Four answer options (A–D)
      - The correct answer key
      - A brief explanation
    """
    try:
        parsed_context = _parse_context(context)

        if file and file.filename:
            # File is provided
            uploaded_files_data = [await _extract_uploaded_file(file)]
            parsed_context["uploaded_files"] = uploaded_files_data

        result = await generate_quiz(
            context=parsed_context,
            num_questions=num_questions,
            difficulty=difficulty,
        )
        return QuizResponse(**result)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in /api/v1/quiz/generate")
        raise HTTPException(status_code=500, detail="Internal server error generating quiz.")


@router.post("/generate/stream")
async def generate_quiz_stream_endpoint(
    context: str = Form("{}", description="JSON string of context data"),
    num_questions: int = Form(5, ge=1, le=30, description="How many questions to generate (1-30)"),
    difficulty: str = Form("intermediate", description="easy, intermediate, or hard"),
    file: Optional[UploadFile] = File(default=None),
):
    """
    Quiz Generator Stream — identical to `/generate` but streams the raw JSON string output as it generates.
    This allows the client to provide immediate feedback and visual progression for the user.
    """
    try:
        parsed_context = _parse_context(context)

        if file and file.filename:
            uploaded_files_data = [await _extract_uploaded_file(file)]
            parsed_context["uploaded_files"] = uploaded_files_data

        # Return stream directly. Format is text/event-stream or application/x-ndjson depending on how the frontend prefers it.
        # We output raw partial JSON text.
        return StreamingResponse(
            generate_quiz_stream(
                context=parsed_context,
                num_questions=num_questions,
                difficulty=difficulty,
            ),
            media_type="text/plain",
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in /api/v1/quiz/generate/stream")
        raise HTTPException(status_code=500, detail="Internal server error generating quiz stream.")


@router.post("/flashcards", response_model=FlashcardResponse)
async def generate_flashcards_endpoint(
    context: str = Form("{}", description="JSON string of context data"),
    num_cards: int = Form(8, ge=1, le=30, description="How many flashcards to generate (1-30)"),
    difficulty: str = Form("intermediate", description="easy, intermediate, or hard"),
    file: Optional[UploadFile] = File(default=None),
):
    """
    Flashcard Generator — create a professional, high-impact study deck from any JSON context.

    **Input:**
    - `context` *(optional)*: JSON string describing the topic, subject matter,
      or structured content the flashcards should be based on.
    - `num_cards`: How many flashcards to generate (1–30, default 8).
    - `difficulty`: "easy", "intermediate", or "hard" (default: "intermediate").
    - `file`: Optional file upload to generate the flashcards from.

    **Output:**
    - A `deck_title` and list of cards, each containing:
      - `front`: {title, body}
      - `back`: {title, body}
    """
    try:
        parsed_context = _parse_context(context)

        if file and file.filename:
            uploaded_files_data = [await _extract_uploaded_file(file)]
            parsed_context["uploaded_files"] = uploaded_files_data

        result = await generate_flashcards(
            context=parsed_context,
            num_cards=num_cards,
            difficulty=difficulty,
        )
        return FlashcardResponse(**result)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in /api/v1/quiz/flashcards")
        raise HTTPException(status_code=500, detail="Internal server error generating flashcards.")


@router.post("/feedback", response_model=QuizFeedbackResponse)
async def feedback_endpoint(request: QuizFeedbackRequest):
    """
    Quiz Feedback — provide detailed performance analysis and learning recommendations.

    **Input:**
    - `context`: JSON object describing the topic/context of the quiz.
    - `results`: List of objects, each containing:
      - `question`: The original question text.
      - `selected_answer`: The answer key (A, B, C, or D) the user chose.
      - `correct_answer`: The actual correct answer key.

    **Output:**
    - `overall_score`: The percentage score.
    - `competency_level`: Professional grade and summary.
    - `analytical_feedback`: Breakdown of strengths, weaknesses, and key clauses.
    - `risk_assessment`: Evaluation of organizational risk based on knowledge gaps.
    - `learning_roadmap`: Prioritized action plan for improvement.
    """
    try:
        result = await generate_quiz_feedback(
            context=request.context,
            results=request.results,
        )
        return QuizFeedbackResponse(**result)
    except Exception as exc:
        logger.exception("Unhandled error in /api/v1/quiz/feedback")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/followup", response_model=FollowupQuestionResponse)
async def generate_followup_endpoint(request: FollowupQuestionRequest):
    """
    Followup Question Generator — create small, related followup questions from the given JSON context.

    **Input:**
    - `context`: JSON object describing the topic/context.
    - `num_questions`: Number of followup questions to generate.

    **Output:**
    - `questions`: A list of thought-provoking followup question strings.
    - `generated_at`: ISO 8601 timestamp.
    """
    try:
        result = await generate_followup_question(
            context=request.context,
            num_questions=request.num_questions,
        )
        return FollowupQuestionResponse(**result)
    except Exception as exc:
        logger.exception("Unhandled error in /api/v1/quiz/followup")
        raise HTTPException(status_code=500, detail=str(exc))
