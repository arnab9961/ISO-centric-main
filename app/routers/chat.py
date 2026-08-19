import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import OPENAI_MODEL
from app.core.models import ChatMessage, ChatRequest, ChatResponse, ISOStandard
from app.core.prompts import GENERAL_CHAT_SYSTEM_PROMPT
from app.core.session import handle_chat
from app.services.benchmark import extract_text_from_file
from app.services.rag import search_similar


router = APIRouter(prefix="/api/v1", tags=["General Chat"])
logger = logging.getLogger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def general_chat(
    messages: str = Form(..., description="User prompt text, or a JSON list of message objects"),
    context: str = Form("{}", description="JSON string of context data"),
    iso_standard: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    """
    General ISO AI Chat — not tied to any specific module.
    Ask anything about ISO standards, compliance, auditing, or best practices.
    Supports multi-turn memory via session_id. Optionally pass any JSON as context or an uploaded file.
    """
    try:
        request_payload = ChatRequest(
            messages=_build_messages(messages),
            context=_parse_context(context),
            iso_standard=_parse_iso_standard(iso_standard),
            session_id=session_id,
        )

        if file:
            content = await file.read()
            try:
                file_text = await extract_text_from_file(file, content)
                request_payload.context = request_payload.context or {}
                request_payload.context["uploaded_file_name"] = file.filename
                request_payload.context["uploaded_file_text"] = file_text
            except Exception as exc:
                logger.warning("File processing error in /api/v1/chat: %s", exc)
                raise HTTPException(status_code=400, detail=f"Failed to process file: {str(exc)}") from exc

        # Retrieve relevant knowledge from vector database
        if request_payload.messages:
            user_query = request_payload.messages[-1].content
            try:
                retrieved_chunks = await search_similar(user_query, top_k=3)
                if retrieved_chunks:
                    request_payload.context = request_payload.context or {}
                    request_payload.context["retrieved_knowledge"] = retrieved_chunks
            except Exception:
                logger.exception("RAG retrieval failed in /api/v1/chat")

        return await handle_chat(
            request=request_payload,
            system_prompt=GENERAL_CHAT_SYSTEM_PROMPT,
            sources=["ISO Standards Knowledge Base"],
            suggested_followups=[
                "Can you give me a practical example?",
                "What are the common non-conformances in this area?",
                "How does this apply to a small organisation?",
                "What documentation is required?",
            ],
            model=OPENAI_MODEL,
            temperature=0.5,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in /api/v1/chat")
        raise HTTPException(status_code=500, detail="Internal server error in chat endpoint.")


def _build_messages(raw_messages: str) -> list[ChatMessage]:
    if not raw_messages or not raw_messages.strip():
        raise HTTPException(status_code=400, detail="messages is required")

    stripped = raw_messages.strip()

    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON in messages") from exc

        if not isinstance(parsed, list):
            raise HTTPException(status_code=400, detail="messages must be a JSON list or plain text")

        built_messages: list[ChatMessage] = []
        for item in parsed:
            if isinstance(item, dict) and isinstance(item.get("content"), str) and item["content"].strip():
                built_messages.append(ChatMessage(content=item["content"]))
            elif isinstance(item, str) and item.strip():
                built_messages.append(ChatMessage(content=item))
            else:
                raise HTTPException(status_code=400, detail="Each message must contain text")

        if not built_messages:
            raise HTTPException(status_code=400, detail="messages cannot be empty")

        return built_messages

    return [ChatMessage(content=stripped)]


def _parse_context(raw_context: str) -> dict[str, Any]:
    if not raw_context or not raw_context.strip():
        return {}

    try:
        parsed_context = json.loads(raw_context)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON in context") from exc

    if not isinstance(parsed_context, dict):
        raise HTTPException(status_code=400, detail="context must be a JSON object")

    return parsed_context


def _parse_iso_standard(raw_iso_standard: Optional[str]) -> Optional[ISOStandard]:
    if raw_iso_standard is None:
        return None

    cleaned_value = raw_iso_standard.strip()
    if not cleaned_value or cleaned_value.lower() == "string":
        return None

    try:
        return ISOStandard(cleaned_value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="iso_standard must be one of the supported ISO values.",
        ) from exc
