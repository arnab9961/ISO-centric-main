from fastapi import APIRouter
import logging

from app.core.config import OPENAI_MODEL
from app.core.models import ChatRequest, ChatResponse, GeneratedDocument, NavigatorRequest
from app.core.prompts import ISO_NAVIGATOR_SYSTEM_PROMPT
from app.core.session import handle_chat
from app.services.navigator import generate_iso_navigator_document

router = APIRouter(prefix="/api/v1/navigator", tags=["ISO Navigator"])
logger = logging.getLogger(__name__)


@router.post("/generate", response_model=GeneratedDocument)
async def generate_iso_document(request: NavigatorRequest):
    """
    ISO Navigator: Generate compliant documentation based on organization context.
    Creates policies, SOPs, risk registers, and other required documents.
    """
    try:
        return await generate_iso_navigator_document(request)
    except Exception:
        logger.exception("Unhandled error in /api/v1/navigator/generate")
        raise


@router.post("/chat", response_model=ChatResponse)
async def navigator_chat(request: ChatRequest):
    """
    ISO Navigator: Conversational consultation for ISO implementation questions.
    Supports multi-turn memory via session_id. Pass context as JSON for tailored guidance.
    """
    try:
        return await handle_chat(
            request=request,
            system_prompt=ISO_NAVIGATOR_SYSTEM_PROMPT,
            sources=["ISO Standards Database"],
            suggested_followups=[
                "Can you elaborate on the implementation steps?",
                "What evidence would an auditor look for?",
                "How does this integrate with other management systems?",
            ],
            model=OPENAI_MODEL,
            temperature=0.5,
        )
    except Exception:
        logger.exception("Unhandled error in /api/v1/navigator/chat")
        raise
