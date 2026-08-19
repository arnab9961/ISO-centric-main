import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.models import IngestResponse
from app.services.benchmark import extract_text_from_file
from app.services.rag import ingest_document


router = APIRouter(prefix="/api/v1", tags=["RAG"])
logger = logging.getLogger(__name__)


@router.post("/ingest", response_model=IngestResponse)
async def ingest_knowledge(
    file: Optional[UploadFile] = File(None),
    text_content: Optional[str] = Form(None),
    metadata: str = Form("{}"),
):
    """
    Ingest documents into the vector database for RAG-enhanced chat.
    Accepts PDF/DOCX/TXT files, raw text, or both simultaneously.
    """
    try:
        if not file and not text_content:
            raise HTTPException(
                status_code=400,
                detail="Either 'file' or 'text_content' must be provided",
            )

        combined_text = ""
        filename = "raw_text"

        if file:
            content = await file.read()
            try:
                file_text = await extract_text_from_file(file, content, max_chars=100000)
                combined_text += file_text
                filename = file.filename or "uploaded_file"
            except Exception as exc:
                logger.warning("File extraction failed in /api/v1/ingest: %s", exc)
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to process file: {str(exc)}",
                ) from exc

        if text_content:
            if combined_text:
                combined_text += "\n\n" + text_content
            else:
                combined_text = text_content

        try:
            parsed_metadata: Dict[str, Any] = json.loads(metadata)
        except json.JSONDecodeError as exc:
            logger.warning("Invalid metadata JSON in /api/v1/ingest: %s", exc)
            raise HTTPException(
                status_code=400,
                detail="Invalid JSON in metadata",
            ) from exc

        result = await ingest_document(
            filename=filename,
            text=combined_text,
            metadata=parsed_metadata,
        )

        return IngestResponse(
            success=result.get("success", False),
            document_id=result.get("document_id"),
            chunks_created=result.get("chunks_created", 0),
            filename=result.get("filename", filename),
            error=result.get("error"),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in /api/v1/ingest")
        raise HTTPException(status_code=500, detail="Internal server error ingesting content.")
