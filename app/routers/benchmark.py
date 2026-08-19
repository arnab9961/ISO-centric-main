import os
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import DEEPSEEK_MODEL_PRO
from app.core.models import (
    BenchmarkAnalysisResponse,
    BenchmarkRequest,
    ChatRequest,
    ChatResponse,
)
from app.core.prompts import BENCHMARK_AI_SYSTEM_PROMPT
from app.core.session import handle_chat
from app.services.benchmark import extract_text_from_file, generate_benchmark_analysis

router = APIRouter(prefix="/api/v1/benchmark", tags=["Benchmark AI"])
logger = logging.getLogger(__name__)

BENCHMARK_MAX_INPUT_CHARS = int(os.getenv("BENCHMARK_MAX_INPUT_CHARS", "15000"))


@router.post("/analyze-text", response_model=BenchmarkAnalysisResponse)
async def analyze_compliance_text(request: BenchmarkRequest):
    """
    Benchmark AI: Analyze text content for ISO compliance.
    Evaluates against ISO requirements, identifies gaps, and grades the document.
    """
    if not request.document_text or len(request.document_text.strip()) < 50:
        raise HTTPException(
            status_code=400,
            detail="document_text is required and must be at least 50 characters.",
        )

    try:
        analysis_id = f"bench_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        result = await generate_benchmark_analysis(
            document_text=request.document_text[:BENCHMARK_MAX_INPUT_CHARS],
            improvement_goal=request.improvement_goal or "General assessment",
            target_standard=request.target_standard or "ISO 9001:2015",
            document_type=request.document_type,
            department=request.department,
            analysis_id=analysis_id,
        )
        return BenchmarkAnalysisResponse(**result)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in /api/v1/benchmark/analyze-text")
        raise HTTPException(status_code=500, detail="Internal server error analyzing text.")


@router.post("/analyze-file", response_model=BenchmarkAnalysisResponse)
async def analyze_compliance_file(
    file: UploadFile = File(...),
    improvement_goal: Optional[str] = Form(None),
    target_standard: str = Form("ISO 9001:2015", description="Target ISO standard to evaluate against"),
    document_type: str = Form("Unknown"),
    department: Optional[str] = Form(None),
):
    """
    Benchmark AI: Upload and analyze a document file for ISO compliance.
    Supports PDF, Word, TXT, and images (PDF text extraction supported; images converted where possible).
    """
    allowed_extensions = [".pdf", ".doc", ".docx", ".txt"]
    file_ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}",
        )

    content = await file.read()

    mime_mapping = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    mime_type = mime_mapping.get(file_ext)

    document_text = ""
    document_content = None

    if mime_type:
        document_content = content
    else:
        document_text = await extract_text_from_file(file, content)
        document_text = document_text[:BENCHMARK_MAX_INPUT_CHARS]
        if len(document_text) < 50:
            raise HTTPException(
                status_code=400,
                detail="Document content too short for meaningful analysis",
            )

    try:
        analysis_id = f"bench_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        result = await generate_benchmark_analysis(
            document_text=document_text if document_text else None,
            document_content=document_content,
            mime_type=mime_type,
            improvement_goal=improvement_goal or "General assessment",
            target_standard=target_standard,
            document_type=document_type,
            department=department,
            analysis_id=analysis_id,
        )
        return BenchmarkAnalysisResponse(**result)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in /api/v1/benchmark/analyze-file")
        raise HTTPException(status_code=500, detail="Internal server error analyzing file.")


@router.post("/chat", response_model=ChatResponse)
async def benchmark_chat(request: ChatRequest):
    """
    Benchmark AI: Chat about analysis results and compliance improvement actions.
    Supports multi-turn memory via session_id. Pass the analysis result as JSON context.
    """
    return await handle_chat(
        request=request,
        system_prompt=BENCHMARK_AI_SYSTEM_PROMPT,
        sources=["ISO Standards"],
        suggested_followups=[
            "How should I prioritize these actions?",
            "What evidence would an auditor look for?",
            "Can you provide a template for this?",
            "How long will implementation take?",
        ],
        model=DEEPSEEK_MODEL_PRO,
        temperature=0.4,
    )
