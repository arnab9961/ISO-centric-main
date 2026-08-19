from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List

from fastapi import HTTPException

from app.core.client import DeepSeekClient
from app.core.config import DEEPSEEK_MODEL, SESSION_STORE
from app.core.models import ChatRequest, ChatResponse
from app.core.token_utils import is_truncated

logger = logging.getLogger(__name__)


async def handle_chat(
    request: ChatRequest,
    system_prompt: str,
    sources: List[str],
    suggested_followups: List[str],
    model: str = DEEPSEEK_MODEL,
    temperature: float = 0.5,
) -> ChatResponse:
    """
    Unified chat handler with multi-turn session memory (SESSION_STORE keyed by session_id).
    Uses the OpenAI-compatible DeepSeek API.
    """
    session_id = request.session_id or str(uuid.uuid4())

    # Build system instruction
    system_instruction = system_prompt
    if request.iso_standard:
        system_instruction += f"\n\nFocus on {request.iso_standard.value} requirements."

    # Embed context directly in the system instruction when provided
    retrieved_knowledge = None
    if request.context:
        # Handle retrieved knowledge from vector database separately
        retrieved_knowledge = request.context.get("retrieved_knowledge")
        context_copy = {k: v for k, v in request.context.items() if k != "retrieved_knowledge"}
        
        if context_copy:
            system_instruction += f"\n\nContext (JSON):\n{json.dumps(context_copy, indent=2)}"
        
        if retrieved_knowledge:
            system_instruction += "\n\nRelevant knowledge from vector database:\n"
            for idx, chunk in enumerate(retrieved_knowledge, 1):
                metadata = chunk.get("metadata", {})
                filename = metadata.get("filename", "unknown")
                chunk_idx = metadata.get("chunk_index", "?")
                similarity = chunk.get("similarity_score", 0)
                text = chunk.get("text", "")
                
                system_instruction += f"\n[Source {idx}: {filename} (chunk {chunk_idx}, similarity: {similarity:.2f})]\n{text}\n"
            
            system_instruction += "\nUse the above retrieved knowledge to enhance your response when relevant."

    # Retrieve or initialise conversation history for this session
    history: List[Dict[str, Any]] = SESSION_STORE.get(session_id, [])

    # Prepend system message (always first, reflecting latest instruction)
    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_instruction}]
    messages.extend(history)

    # Append new user message(s) from this request
    for msg in request.messages:
        messages.append({"role": "user", "content": msg.content})

    client = DeepSeekClient.get_async_client()
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=8192,
            ),
            timeout=180,
        )
    except asyncio.TimeoutError:
        logger.error("Chat response timed out for session %s", session_id)
        raise HTTPException(
            status_code=504,
            detail="Chat response timed out. Please retry or simplify your question.",
        )
    except Exception as e:
        logger.exception("Chat generation failed for session %s", session_id)
        raise HTTPException(status_code=500, detail=f"Chat generation failed: {str(e)}")

    assistant_content: str = response.choices[0].message.content
    finish_reason = response.choices[0].finish_reason
    
    # If response was truncated, keep completing until naturally finished
    max_continuations = 3
    continuation_count = 0
    
    while is_truncated(finish_reason) and continuation_count < max_continuations:
        continuation_count += 1
        logger.info(f"Response truncated for session {session_id}, continuation {continuation_count}...")
        
        # Use last ~500 chars as context to continue seamlessly
        context_tail = assistant_content[-500:] if len(assistant_content) > 500 else assistant_content
        
        completion_messages = [
            {"role": "system", "content": "Continue the following text seamlessly. Do not repeat what was already said. Just continue from where it left off and complete the thought naturally. Do not add any preamble or introduction."},
            {"role": "user", "content": f"...{context_tail}"}
        ]
        
        try:
            completion_response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=completion_messages,
                    temperature=temperature,
                    max_tokens=2048,
                ),
                timeout=60,
            )
            completion_text = completion_response.choices[0].message.content.strip()
            finish_reason = completion_response.choices[0].finish_reason
            
            if completion_text:
                # Remove any repetition of the context tail
                cleaned = _remove_overlap(assistant_content, completion_text)
                assistant_content = assistant_content.rstrip() + " " + cleaned
                    
        except Exception as e:
            logger.warning(f"Failed to complete truncated response: {str(e)}")
            break

    # Persist the new user turns and the assistant reply to session history
    for msg in request.messages:
        history.append({"role": "user", "content": msg.content})
    history.append({"role": "assistant", "content": assistant_content})
    SESSION_STORE[session_id] = history

    # Add vector database to sources if knowledge was retrieved
    final_sources = sources.copy()
    if retrieved_knowledge:
        if "Vector Database" not in final_sources:
            final_sources.insert(0, "Vector Database")

    return ChatResponse(
        response=assistant_content,
        sources=final_sources,
        suggested_followups=suggested_followups,
        session_id=session_id,
    )


def _remove_overlap(original: str, continuation: str) -> str:
    """Remove any overlapping text between original ending and continuation start."""
    if not continuation:
        return continuation
    
    # Try to find overlap by checking if continuation starts with end of original
    for overlap_len in range(min(100, len(original), len(continuation)), 0, -1):
        if original.endswith(continuation[:overlap_len]):
            return continuation[overlap_len:].lstrip()
    
    # Check for partial word overlap at boundary
    original_words = original.split()[-10:] if original else []
    continuation_words = continuation.split()[:10] if continuation else []
    
    for i in range(min(len(original_words), len(continuation_words)), 0, -1):
        if original_words[-i:] == continuation_words[:i]:
            return " ".join(continuation.split()[i:])
    
    return continuation
