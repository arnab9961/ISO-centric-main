from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, Optional

from fastapi import HTTPException, UploadFile

from app.core.client import DeepSeekClient
from app.core.config import DEEPSEEK_MODEL_PRO
from app.core.prompts import BENCHMARK_AI_SYSTEM_PROMPT
from app.core.token_utils import is_truncated, get_json_wrap_message, attempt_json_repair
from app.services.rag import search_similar

logger = logging.getLogger(__name__)


BENCHMARK_MAX_INPUT_CHARS = int(os.getenv("BENCHMARK_MAX_INPUT_CHARS", "15000"))
BENCHMARK_TIMEOUT_SECONDS = int(os.getenv("BENCHMARK_TIMEOUT_SECONDS", "150"))
FILE_EXTRACT_MAX_CHARS = int(os.getenv("FILE_EXTRACT_MAX_CHARS", "30000"))


def get_iso_clause_structure(standard: str) -> str:
    """Return the clause structure text for a given ISO standard."""
    structures = {
        "ISO 9001:2015": "4.1 Context | 4.2 Interested parties | 4.3 Scope | 4.4 Processes | 5.1 Leadership | 5.2 Policy | 5.3 Roles | 6.1 Risks | 6.2 Objectives | 6.3 Changes | 7.1 Resources | 7.2 Competence | 7.3 Awareness | 7.4 Communication | 7.5 Documented info | 8.1 Operations | 8.2 Requirements | 8.3 Design | 8.4 External providers | 8.5 Service provision | 8.6 Release | 8.7 Nonconforming outputs | 9.1 Monitoring | 9.2 Internal audit | 9.3 Management review | 10.1 General | 10.2 Corrective action | 10.3 Continual improvement",
        "ISO 27001:2022": "4 Context | 5 Leadership | 6 Planning | 7 Support | 8 Operation | 9 Performance Evaluation | 10 Improvement | Annex A: 93 information security controls (4 themes)",
        "ISO 14001:2015": "4 Context | 5 Leadership | 6 Planning | 7 Support | 8 Operation | 9 Performance Evaluation | 10 Improvement",
        "ISO 45001:2018": "4 Context | 5 Leadership & Worker Participation | 6 Planning | 7 Support | 8 Operation | 9 Performance Evaluation | 10 Improvement",
    }
    return structures.get(standard, "Standard clause structure not available")


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}..."


async def extract_text_from_file(
    file: UploadFile,
    content: bytes,
    max_chars: int = FILE_EXTRACT_MAX_CHARS,
) -> str:
    """Extract text from uploaded file (text/Word/PDF supported; images not supported)."""
    file_ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""

    if file_ext in [".txt", ".md"]:
        return _truncate_text(content.decode("utf-8", errors="ignore"), max_chars)

    if file_ext in [".doc", ".docx"]:
        try:
            from docx import Document
            doc = Document(BytesIO(content))
            return _truncate_text("\n".join([p.text for p in doc.paragraphs]), max_chars)
        except Exception as e:
            return f"[Word extraction failed: {str(e)}]"

    if file_ext == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(BytesIO(content))
            parts = []
            total_chars = 0
            for page in reader.pages:
                page_text = page.extract_text() or ""
                if not page_text:
                    continue
                remaining = max_chars - total_chars
                if remaining <= 0:
                    break
                if len(page_text) > remaining:
                    page_text = page_text[:remaining]
                parts.append(page_text)
                total_chars += len(page_text)
                if total_chars >= max_chars:
                    break
            return "\n\n".join(parts)
        except Exception as e:
            return f"[PDF extraction failed: {str(e)}]"

    # Images and unsupported formats
    return f"[Binary file type '{file_ext}' cannot be processed as text. Please convert to PDF or text first.]"


async def generate_benchmark_analysis(
    document_text: Optional[str] = None,
    document_content: Optional[bytes] = None,
    mime_type: Optional[str] = None,
    improvement_goal: str = "General assessment",
    target_standard: str = "ISO 9001:2015",
    document_type: str = "Unknown",
    department: Optional[str] = None,
    analysis_id: str = "",
) -> Dict[str, Any]:
    """Generate a complete ISO benchmark analysis using the DeepSeek API."""

    if not document_text and not document_content:
        raise HTTPException(
            status_code=400,
            detail="No document content provided for analysis.",
        )

    clause_structure = get_iso_clause_structure(target_standard)

    rag_context_text = ""
    query_parts = [target_standard, improvement_goal]
    if document_type != "Unknown":
        query_parts.append(document_type)
    if department:
        query_parts.append(department)
    
    try:
        query = " ".join(query_parts)
        similar_docs = await search_similar(query, top_k=3)
        if similar_docs:
            rag_context_text = "RELEVANT VECTOR DB CONTEXT:\n" + "\n".join(
                f"- {doc['text']}" for doc in similar_docs
            )
    except Exception as e:
        logger.warning(f"RAG search failed: {e}")

    # Compact output instructions instead of verbose schema (saves ~600 prompt tokens)
    compact_output_instructions = """
Respond ONLY with a JSON object containing exactly these fields:
- overall_score (int 0-100)
- grade ("A"|"B+"|"B"|"C+"|"C"|"D"|"F")
- compliance_percentage (int 0-100)
- effectiveness_percentage (int 0-100)
- document_type_detected (string)
- standard_analyzed (string)
- clause_compliance: array of {clause_number, clause_title, status("Conforming"|"Minor Gap"|"Major Gap"|"Non-Conforming"), compliance_percentage, evidence_found, gap_description, recommendation} (MAXIMUM 5 CLAUSES)
- strengths: array of 3-5 strings
- identified_gaps: array of {priority("High Priority"|"Medium Priority"|"Low Priority"), clause_reference, gap_title, gap_description, risk_level("High"|"Medium"|"Low"), iso_requirement} (MAXIMUM 5 GAPS)
- recommendations: array of {priority, clause_reference, title, description, benefit_statement, effort_level("Low"|"Medium"|"High"), estimated_timeline} (MAXIMUM 5 RECOMMENDATIONS)
- word_count_analyzed (int)
- conversation_id (string)
"""

    prompt = f"""
DOCUMENT ANALYSIS REQUEST
=========================

DOCUMENT INFORMATION:
- Type: {document_type}
- Department: {department if department else 'Not specified'}
- Improvement Goal: {improvement_goal}

ISO STANDARD: {target_standard}

CLAUSE STRUCTURE TO EVALUATE:
{clause_structure}

TASK:
Perform comprehensive ISO compliance analysis and return structured JSON matching the schema.

IMPORTANT: If no specific ISO standard is explicitly requested, you MUST prioritize and evaluate against the latest relative ISO standards based on the document's context.

ANALYSIS REQUIREMENTS:
1. OVERALL SCORING — overall_score (0-100), grade, compliance_percentage, effectiveness_percentage
2. CLAUSE-BY-CLAUSE — clause_number, clause_title, status, compliance_percentage... (ONLY evaluate the top 5 most relevant clauses)
3. STRENGTHS — 3-5 specific strengths
4. IDENTIFIED GAPS — priority, clause_reference, gap_title... (MAXIMUM 5 gaps)
5. RECOMMENDATIONS — priority, clause_reference, title... (MAXIMUM 5 recommendations)
6. METADATA — word_count_analyzed, conversation_id: "{analysis_id}"

CRITICAL: To prevent timeouts, your JSON arrays for clauses, gaps, and recommendations MUST NOT EXCEED 5 ITEMS EACH.

RESPOND ONLY WITH VALID JSON MATCHING THE SCHEMA.
"""

    contents_text = [prompt]

    if rag_context_text:
        contents_text.append(rag_context_text)

    if document_text:
        contents_text.append(
            f"DOCUMENT CONTENT (TEXT):\n{document_text[:BENCHMARK_MAX_INPUT_CHARS]}"
        )

    if document_content and mime_type:
        # Binary content cannot be sent directly; attempt text extraction fallback
        if mime_type == "application/pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(BytesIO(document_content))
                pages = [page.extract_text() or "" for page in reader.pages]
                extracted = "\n\n".join(pages)
                if extracted.strip():
                    contents_text.append(
                        "DOCUMENT CONTENT (extracted from PDF):\n"
                        f"{extracted[:BENCHMARK_MAX_INPUT_CHARS]}"
                    )
            except Exception:
                pass  # Best-effort; analysis proceeds on whatever text is available
        # Images and other binary types are not supported; skip silently

    combined_prompt = "\n\n".join(contents_text)

    client = DeepSeekClient.get_async_client()
    try:
        full_system_instruction = (
            BENCHMARK_AI_SYSTEM_PROMPT
            + compact_output_instructions
        )
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=DEEPSEEK_MODEL_PRO,
                messages=[
                    {
                        "role": "system",
                        "content": full_system_instruction,
                    },
                    {"role": "user", "content": combined_prompt},
                ],
                temperature=0.1,
                max_tokens=4096,
                response_format={"type": "json_object"},
            ),
            timeout=BENCHMARK_TIMEOUT_SECONDS,
        )
        content = response.choices[0].message.content
        finish_reason = response.choices[0].finish_reason
        
        if is_truncated(finish_reason):
            logger.warning("Benchmark analysis response was truncated at token limit")
        
        # Parse JSON with repair attempt if needed
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            try:
                result = attempt_json_repair(content)
                logger.info("Successfully repaired truncated benchmark JSON")
            except ValueError:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "The AI returned an incomplete response. This usually means the document "
                        "is too large. Try truncating to the most relevant sections and retry."
                    ),
                )
        
        result["standard_analyzed"] = target_standard
        result["analysis_timestamp"] = datetime.utcnow().isoformat()
        result["analysis_id"] = analysis_id
        
        # Add truncation warning if detected
        if is_truncated(finish_reason):
            result["_was_truncated"] = True
            result["_truncation_warning"] = get_json_wrap_message()
        
        return result
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=(
                "Benchmark analysis timed out while waiting for the AI provider. "
                "Try a shorter document or retry shortly."
            ),
        )
    except json.JSONDecodeError:
        # This should not be reached anymore since we handle it above with repair
        raise HTTPException(
            status_code=502,
            detail=(
                "The AI returned an incomplete response. This usually means the document "
                "is too large. Try truncating to the most relevant sections and retry."
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Benchmark analysis failed: {str(e)}")
