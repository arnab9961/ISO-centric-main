import os
import logging
from typing import Optional, Tuple

from fastapi import APIRouter, HTTPException, Request
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.models import (
    AdvancedIsoSuggestionRequest,
    IsoSuggestionRequest,
    IsoSuggestionResponse,
    OrgContextRequest,
    OrgContextResponse,
)
from app.services.discovery import (
    generate_org_context,
    suggest_advanced_iso_standards,
    suggest_iso_standards,
)
from app.services.benchmark import extract_text_from_file

router = APIRouter(prefix="/api/v1/discovery", tags=["Discovery"])
logger = logging.getLogger(__name__)


@router.post("/context-generator", response_model=OrgContextResponse)
async def api_generate_org_context(request: OrgContextRequest):
    """
    Step 1: Organization Context Generator
    Scrapes a URL (or accepts text) and returns 3 structured context mappings 
    (What, Where, Why, When, Whom).
    """
    try:
        return await generate_org_context(request)
    except ValueError as e:
        logger.warning("Validation error in /api/v1/discovery/context-generator: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Unhandled error in /api/v1/discovery/context-generator")
        raise HTTPException(status_code=500, detail="Internal server error generating context.")


ALLOWED_SUGGESTION_FILE_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md"}


async def _parse_iso_suggestion_request(request: Request) -> Tuple[IsoSuggestionRequest, Optional[str], Optional[str]]:
    content_type = request.headers.get("content-type", "").lower()

    if content_type.startswith("multipart/form-data") or content_type.startswith("application/x-www-form-urlencoded"):
        form = await request.form()
        category = form.get("category")
        file = form.get("file")
        document_text = None
        file_name = None

        if isinstance(file, StarletteUploadFile) and file.filename:
            file_name = file.filename
            file_ext = os.path.splitext(file.filename)[1].lower()
            if file_ext not in ALLOWED_SUGGESTION_FILE_EXTENSIONS:
                allowed = ", ".join(sorted(ALLOWED_SUGGESTION_FILE_EXTENSIONS))
                raise ValueError(f"Unsupported file type. Allowed: {allowed}")

            content = await file.read()
            document_text = await extract_text_from_file(file, content)
            if document_text.startswith("[") and "failed:" in document_text.lower():
                raise ValueError(document_text)

        return (
            IsoSuggestionRequest(category=str(category).strip() if category else None),
            document_text,
            file_name,
        )

    try:
        payload = await request.json()
    except Exception as exc:
        raise ValueError("Request body must be valid JSON or multipart form data.") from exc

    return IsoSuggestionRequest(**payload), None, None


@router.post(
    "/iso-suggestions",
    response_model=IsoSuggestionResponse,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "description": "Category or industry",
                            }
                        },
                    }
                },
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string"},
                            "file": {
                                "type": "string",
                                "format": "binary",
                                "description": "Optional PDF, Word, TXT, or Markdown file",
                            },
                        },
                    }
                },
            }
        }
    },
)
async def api_suggest_iso_standards(request: Request):
    """
    Step 2: ISO Standard Suggestion
    Suggests 3-5 relevant ISO standards based on an input category (e.g., security, manufacturing).
    Also accepts multipart/form-data with category and an optional file (PDF, Word, TXT, or Markdown).
    """
    try:
        suggestion_request, document_text, file_name = await _parse_iso_suggestion_request(request)
        return await suggest_iso_standards(
            suggestion_request,
            document_text=document_text,
            file_name=file_name,
        )
    except ValueError as e:
        logger.warning("Validation error in /api/v1/discovery/iso-suggestions: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Unhandled error in /api/v1/discovery/iso-suggestions")
        raise HTTPException(status_code=500, detail="Internal server error suggesting standards.")


@router.post("/iso-suggestions/advanced", response_model=IsoSuggestionResponse)
async def api_suggest_advanced_iso_standards(request: AdvancedIsoSuggestionRequest):
    """
    Suggests 3-5 relevant ISO standards based on industry, management level, and department.
    """
    try:
        return await suggest_advanced_iso_standards(request)
    except ValueError as e:
        logger.warning("Validation error in /api/v1/discovery/iso-suggestions/advanced: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Unhandled error in /api/v1/discovery/iso-suggestions/advanced")
        raise HTTPException(status_code=500, detail="Internal server error suggesting standards.")
