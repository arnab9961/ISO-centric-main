from __future__ import annotations

import re
from datetime import datetime

from app.core.config import DEEPSEEK_MODEL, DEEPSEEK_MODEL_PRO
from app.core.models import GeneratedDocument, NavigatorRequest
from app.core.prompts import ISO_NAVIGATOR_SYSTEM_PROMPT
from app.core.token_utils import is_truncated, get_text_wrap_message
from app.services.deepseek import generate_with_deepseek
from app.services.rag import search_similar
import logging

logger = logging.getLogger(__name__)


async def generate_iso_navigator_document(request: NavigatorRequest) -> GeneratedDocument:
    """ISO Navigator: Generate compliant ISO documentation."""

    org_context = request.organization_context or "Not provided"
    out_type = request.output_type or "ISO Document"
    spec_reqs = request.specific_requirements or "Follow standard ISO requirements for this document type"
    tone = request.tone or "professional"
    language = request.language or "English"

    extra_inputs = request.model_extra or {}
    
    # Dynamically format extra inputs as context/requirements
    extra_context_str = ""
    if extra_inputs:
        extra_context_str = "\nADDITIONAL INPUTS & CONTEXT:\n" + "\n".join(
            f"- {key.replace('_', ' ').title()}: {val}" for key, val in extra_inputs.items()
        )

    prompt = f"""
ORGANIZATION CONTEXT:
{org_context}
{extra_context_str}

TASK:
Generate a {out_type} aligned with applicable ISO management system standards.

SPECIFIC REQUIREMENTS:
{spec_reqs}

DOCUMENT REQUIREMENTS:
1. Include document control information (version, effective date, owner)
2. Reference specific ISO clause numbers relevant to this document type
3. Include purpose, scope, responsibilities, procedures
4. Add measurable objectives and KPIs where applicable
5. Include implementation guidance
6. Use {tone} tone in {language} language

Generate the complete output as a formal Markdown document only.
Follow this structure exactly:
1. Purpose
2. Scope
3. Terms and Definitions
4. Roles and Responsibilities
5. Policy / Procedure Requirements
6. Related Documentation
7. Document Revision History

IMPORTANT: If no specific ISO standard is explicitly requested in the context, you MUST prioritize and use the latest relative ISO standards applicable to this document.

Under section 5, organize the content with logical subheadings such as 5.1, 5.2, and so on.
Use actionable language such as shall, must, and is responsible for.
Do not include introductory or concluding filler.
"""

    try:
        query = f"{out_type} {spec_reqs}"
        similar_docs = await search_similar(query, top_k=5)
        if similar_docs:
            rag_context = "\n\nRELEVANT VECTOR DB CONTEXT:\n" + "\n".join(
                f"- {doc['text']}" for doc in similar_docs
            )
            prompt += rag_context
    except Exception as e:
        logger.warning(f"RAG search failed: {e}")

    context_length = len(org_context) + sum(len(str(v)) for v in extra_inputs.values())
    model = DEEPSEEK_MODEL_PRO if context_length > 1000 else DEEPSEEK_MODEL
    content, finish_reason = await generate_with_deepseek(
        prompt=prompt,
        system_instruction=ISO_NAVIGATOR_SYSTEM_PROMPT,
        model=model,
        max_tokens=4096,
    )
    
    # Handle truncation
    from app.core.token_utils import is_truncated
    if is_truncated(finish_reason):
        content += "\n\n[Note: Response truncated due to token limit]"
    
    # Append truncation note if response was cut off
    confidence_score = 0.85
    if is_truncated(finish_reason):
        content += get_text_wrap_message()
        confidence_score -= 0.15  # Reduce confidence for truncated documents

    clause_matches = re.findall(
        r"(?:Clause|Section|ISO\s*\d+\.\d+)[\s:]*(\d+(?:\.\d+)*)", content, re.IGNORECASE
    )
    iso_clauses = list(set(clause_matches))[:10]

    # Construct metadata with standard fields and merge any extra fields
    metadata = {
        "organization_context": org_context[:200] + "..." if len(org_context) > 200 else org_context,
        "output_type": out_type,
        "tone": tone,
        "language": language,
    }
    for key, val in extra_inputs.items():
        metadata[key] = val

    return GeneratedDocument(
        title=f"{out_type}",
        content=content,
        metadata=metadata,
        iso_clauses_referenced=iso_clauses or ["4.0", "5.0", "6.0", "7.0", "8.0", "9.0", "10.0"],
        generation_timestamp=datetime.utcnow().isoformat(),
        word_count=len(content.split()),
        confidence_score=confidence_score,
    )
