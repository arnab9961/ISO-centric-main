from fastapi import APIRouter, HTTPException
import logging

from app.core.config import DEEPSEEK_MODEL
from app.core.models import (
    AuditContextResponse,
    AuditLensStepRequest,
    AuditLensStepResponse,
    ChatRequest,
    ChatResponse,
    OrgContextRequest,
)
from app.core.prompts import AUDIT_LENS_SYSTEM_PROMPT
from app.core.session import handle_chat
from app.services.audit_lens import generate_audit_context, generate_audit_step

router = APIRouter(prefix="/api/v1/audit-lens", tags=["Audit Lens"])
logger = logging.getLogger(__name__)


@router.post("/context", response_model=AuditContextResponse)
async def get_audit_context(request: OrgContextRequest):
    """
    Phase 1: Context Establishment
    Scrapes URL or text and generates 3 Scope/Criteria/Objective options for the audit.
    """
    try:
        return await generate_audit_context(request)
    except ValueError as e:
        logger.warning("Validation error in /api/v1/audit-lens/context: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Unhandled error in /api/v1/audit-lens/context")
        raise HTTPException(status_code=500, detail="Internal server error generating audit context.")


@router.post("/step", response_model=AuditLensStepResponse)
async def get_audit_step(request: AuditLensStepRequest):
    """
    Phase 2: 13-Step Educational Journey
    Generates guidance and template preview for a specific audit step (1-13).
    """
    try:
        return await generate_audit_step(request)
    except ValueError as e:
        logger.warning("Validation error in /api/v1/audit-lens/step: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Unhandled error in /api/v1/audit-lens/step")
        raise HTTPException(status_code=500, detail=f"Internal server error generating step {request.step_number}.")


@router.post("/chat", response_model=ChatResponse)
async def audit_lens_chat(request: ChatRequest):
    """
    Audit Lens: Chat about audit findings, compliance gaps, or regulatory requirements.
    """
    return await handle_chat(
        request=request,
        system_prompt=AUDIT_LENS_SYSTEM_PROMPT,
        sources=["ISO 19011:2018 Guidelines", "ISO Standards"],
        suggested_followups=[
            "How would an auditor verify this?",
            "Suggest a root cause analysis approach.",
            "What is the standard requirement for this finding?",
            "How long should corrective action take?",
        ],
        model=DEEPSEEK_MODEL,
        temperature=0.4,
    )
