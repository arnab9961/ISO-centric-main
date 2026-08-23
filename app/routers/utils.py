from datetime import datetime
import logging

from fastapi import APIRouter, HTTPException

from app.core.client import OpenAIClient
from app.core.config import OPENAI_MODEL
from app.core.models import ISOStandard
from app.services.benchmark import get_iso_clause_structure

router = APIRouter(tags=["Utilities"])
logger = logging.getLogger(__name__)


@router.get("/")
async def root():
    """Health check and API info."""
    return {
        "message": "ISO Standards AI Assistant API is running",
        "version": "2.0.0",
        "modules": ["ISO Navigator", "Audit Lens", "Benchmark AI"],
        "openai_model": OPENAI_MODEL,
        "documentation": "/docs",
    }


@router.get("/api/v1/health")
async def health_check():
    """Detailed health check with OpenAI connectivity."""
    try:
        client = OpenAIClient.get_async_client()
        test_response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": "Respond with 'OK' if connection successful"}],
            max_completion_tokens=10,
        )
        openai_status = "connected" if test_response.choices[0].message.content else "error"
    except Exception as e:
        logger.exception("Health check OpenAI connectivity failed")
        openai_status = f"error: {str(e)}"

    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "openai_api": openai_status,
        "model": OPENAI_MODEL,
    }


@router.get("/api/v1/standards/list")
async def list_supported_standards():
    """List all supported ISO standards."""
    return {
        "standards": [
            {
                "code": std.value,
                "name": std.value,
                "description": _get_standard_description(std),
            }
            for std in ISOStandard
        ]
    }


@router.get("/api/v1/standards/{standard_code}/clauses")
async def get_standard_clauses(standard_code: str):
    """Get clause structure for a specific ISO standard."""
    clauses = get_iso_clause_structure(standard_code)
    if not clauses or clauses == "Standard clause structure not available":
        raise HTTPException(status_code=404, detail="Standard not found")
    return {
        "standard": standard_code,
        "clauses": clauses,
        "total_clauses": len(clauses.split("\n")),
    }


def _get_standard_description(std: ISOStandard) -> str:
    descriptions = {
        ISOStandard.ISO_9001_2015: "Quality Management Systems - Requirements",
        ISOStandard.ISO_27001_2022: "Information Security Management Systems - Requirements",
        ISOStandard.ISO_14001_2015: "Environmental Management Systems - Requirements",
        ISOStandard.ISO_45001_2018: "Occupational Health and Safety Management Systems",
        ISOStandard.ISO_22301_2019: "Business Continuity Management Systems",
        ISOStandard.ISO_50001_2018: "Energy Management Systems",
    }
    return descriptions.get(std, "ISO Management System Standard")
