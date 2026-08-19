from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

from app.core.config import DEEPSEEK_MODEL
from app.core.models import (
    AuditContextOption,
    AuditContextResponse,
    AuditLensStepRequest,
    AuditLensStepResponse,
    OrgContextRequest,
)
from app.core.prompts import AUDIT_LENS_CONTEXT_PROMPT, AUDIT_LENS_STEP_PROMPT
from app.core.token_utils import is_truncated
from app.services.deepseek import generate_with_deepseek
from app.services.discovery import scrape_url
from app.services.rag import search_similar

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 13-Step Audit Journey Definition
# ---------------------------------------------------------------------------

AUDIT_STEPS = {
    1: {"title": "Initiate the Audit", "stage": "Plan"},
    2: {"title": "Document Review", "stage": "Plan"},
    3: {"title": "Audit Plan", "stage": "Plan"},
    4: {"title": "Work Assignment", "stage": "Plan"},
    5: {"title": "Prepare Working Papers", "stage": "Plan"},
    6: {"title": "Sequence & Scheduling", "stage": "Do"},
    7: {"title": "Opening Meeting", "stage": "Do"},
    8: {"title": "Review & Communicate", "stage": "Do"},
    9: {"title": "Carry out the Audit", "stage": "Do"},
    10: {"title": "Generate Findings", "stage": "Check"},
    11: {"title": "Closing Meeting", "stage": "Check"},
    12: {"title": "Audit Report", "stage": "Check"},
    13: {"title": "Follow Up", "stage": "Act"},
}


async def generate_audit_context(request: OrgContextRequest) -> AuditContextResponse:
    """
    Phase 1: Context Establishment
    Analyzes URL or text and generates 3 Scope/Criteria/Objective options.
    """
    content = ""
    if request.url:
        content = await scrape_url(request.url)
    elif request.text:
        content = request.text

    if not content:
        raise ValueError("Either text or a valid URL must be provided.")

    prompt = f"Organization Information:\n{content}\n\nTask: Generate 5 audit framework options.\nIMPORTANT: You MUST prioritize and suggest frameworks based on the ISO standards explicitly mentioned in the RELEVANT VECTOR DB CONTEXT. Only if the vector context is insufficient should you fall back to suggesting the latest relative ISO standards from your general knowledge applicable to the organization."

    try:
        query = f"ISO management system standards frameworks guidelines requirements for {content[:300]}"
        similar_docs = await search_similar(query, top_k=5)
        if similar_docs:
            rag_context = "\n\nRELEVANT VECTOR DB CONTEXT:\n" + "\n".join(
                f"- {doc['text']}" for doc in similar_docs
            )
            prompt += rag_context
    except Exception as e:
        logger.warning(f"RAG search failed: {e}")

    response_text, finish_reason = await generate_with_deepseek(
        prompt=prompt,
        system_instruction=AUDIT_LENS_CONTEXT_PROMPT,
        model=DEEPSEEK_MODEL,
        temperature=0.7,
        response_format={"type": "json_object"},
    )

    # Clean up markdown wrappers if present
    response_text = response_text.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(response_text)
        options = [AuditContextOption(**opt) for opt in data.get("options", [])]
        
        if is_truncated(finish_reason):
            logger.warning("Audit context generation response was truncated at token limit")
            # Add warning option
            from app.core.token_utils import get_json_wrap_message
            options.append(AuditContextOption(
                scope="⚠️ Truncation Warning",
                criteria=get_json_wrap_message(),
                objective="Response was cut off due to token limits"
            ))
        
        return AuditContextResponse(options=options)
    except Exception as e:
        logger.error(f"Failed to parse audit context options: {e}. Output: {response_text}")
        raise ValueError("Failed to generate audit context options.")


async def generate_audit_step(request: AuditLensStepRequest) -> AuditLensStepResponse:
    """
    Phase 2: 13-Step Educational Journey
    Generates guidance and template preview for a specific audit step.
    """
    step_info = AUDIT_STEPS.get(request.step_number)
    if not step_info:
        raise ValueError(f"Invalid step number: {request.step_number}")

    prompt = AUDIT_LENS_STEP_PROMPT.format(
        step_number=request.step_number,
        step_title=step_info["title"],
        stage=step_info["stage"],
        scope=request.locked_context.scope,
        criteria=request.locked_context.criteria,
        objective=request.locked_context.objective,
    )

    try:
        query = f"{request.locked_context.criteria} {step_info['title']} audit"
        similar_docs = await search_similar(query, top_k=3)
        if similar_docs:
            rag_context = "\n\nRELEVANT VECTOR DB CONTEXT:\n" + "\n".join(
                f"- {doc['text']}" for doc in similar_docs
            )
            prompt += rag_context
    except Exception as e:
        logger.warning(f"RAG search failed: {e}")

    response_text, finish_reason = await generate_with_deepseek(
        prompt=prompt,
        system_instruction="You are a JSON output generator for ISO audit materials.",
        model=DEEPSEEK_MODEL,
        temperature=0.5,
        response_format={"type": "json_object"},
    )

    response_text = response_text.replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(response_text)
        
        guidance = data.get("guidance", "")
        template_preview = data.get("template_preview", "")
        
        if is_truncated(finish_reason):
            logger.warning(f"Audit step {request.step_number} generation response was truncated at token limit")
            from app.core.token_utils import get_json_wrap_message
            truncation_note = f"\n\n{get_json_wrap_message()}"
            guidance += truncation_note
            template_preview += truncation_note
        
        return AuditLensStepResponse(
            step_number=request.step_number,
            title=step_info["title"],
            stage=step_info["stage"],
            guidance=guidance,
            template_preview=template_preview,
            next_step_available=request.step_number < 13,
        )
    except Exception as e:
        logger.error(f"Failed to parse audit step response: {e}. Output: {response_text}")
        raise ValueError(f"Failed to generate materials for step {request.step_number}.")
