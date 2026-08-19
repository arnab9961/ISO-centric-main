from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException

from app.core.client import DeepSeekClient
from app.core.config import DEEPSEEK_MODEL, DEEPSEEK_MODEL_PRO

logger = logging.getLogger(__name__)


DEEPSEEK_CALL_TIMEOUT = 590  # seconds — must be less than DEEPSEEK_TIMEOUT_SECONDS in client.py


async def generate_with_deepseek(
    prompt: str,
    system_instruction: str,
    model: str = DEEPSEEK_MODEL,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    response_format: Optional[Dict[str, str]] = None,
) -> Tuple[str, str]:
    """Generate free-text content using the DeepSeek API. Returns (content, finish_reason) tuple."""
    client = DeepSeekClient.get_async_client()
    try:
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = await asyncio.wait_for(
            client.chat.completions.create(**kwargs),
            timeout=DEEPSEEK_CALL_TIMEOUT,
        )
        content = response.choices[0].message.content
        finish_reason = response.choices[0].finish_reason
        
        if finish_reason == "length":
            logger.warning(f"AI response truncated at {max_tokens} tokens (generate_with_deepseek)")
        
        return content, finish_reason
    except asyncio.TimeoutError:
        logger.error("DeepSeek text generation timed out after %ss", DEEPSEEK_CALL_TIMEOUT)
        raise HTTPException(
            status_code=504,
            detail="AI generation timed out. Please try with a shorter request or retry shortly.",
        )
    except Exception as e:
        logger.exception("DeepSeek text generation failed")
        raise HTTPException(status_code=500, detail=f"DeepSeek API Error: {str(e)}")


async def analyze_with_deepseek(
    prompt: str,
    system_instruction: str,
    response_schema: Dict[str, Any],
    model: str = DEEPSEEK_MODEL_PRO,
    max_tokens: int = 8192,
) -> Tuple[Dict[str, Any], str]:
    """Analyze content using the DeepSeek API with structured JSON output. Returns (parsed_dict, finish_reason) tuple."""
    client = DeepSeekClient.get_async_client()
    try:
        schema_str = json.dumps(response_schema, indent=2)
        full_system_instruction = (
            system_instruction
            + "\n\nYou MUST respond with valid JSON only, matching the required schema exactly.\n\nREQUIRED SCHEMA:\n"
            + schema_str
        )
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": full_system_instruction,
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            ),
            timeout=DEEPSEEK_CALL_TIMEOUT,
        )
        content = response.choices[0].message.content
        finish_reason = response.choices[0].finish_reason
        
        if finish_reason == "length":
            logger.warning(f"AI response truncated at {max_tokens} tokens (analyze_with_deepseek)")
        
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            # Try to repair truncated JSON
            from app.core.token_utils import attempt_json_repair
            try:
                parsed = attempt_json_repair(content)
                logger.info("Successfully repaired truncated JSON response")
            except ValueError:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to parse AI response as JSON: {str(e)}"
                )
        
        return parsed, finish_reason
    except asyncio.TimeoutError:
        logger.error("DeepSeek structured analysis timed out after %ss", DEEPSEEK_CALL_TIMEOUT)
        raise HTTPException(
            status_code=504,
            detail="AI analysis timed out. Please try with a shorter document or retry shortly.",
        )
    except Exception as e:
        logger.exception("DeepSeek structured analysis failed")
        raise HTTPException(status_code=500, detail=f"DeepSeek API Error: {str(e)}")


async def analyze_stream_with_deepseek(
    prompt: str,
    system_instruction: str,
    response_schema: Dict[str, Any],
    model: str = DEEPSEEK_MODEL_PRO,
    max_tokens: int = 8192,
):
    """Analyze content using the DeepSeek API with structured JSON output, streaming the partial JSON string."""
    client = DeepSeekClient.get_async_client()
    try:
        schema_str = json.dumps(response_schema, indent=2)
        full_system_instruction = (
            system_instruction
            + "\n\nYou MUST respond with valid JSON only, matching the required schema exactly.\n\nREQUIRED SCHEMA:\n"
            + schema_str
        )
        # We don't wrap the entire async iteration in a single asyncio.wait_for for simplicity.
        # DeepSeek client's internal timeout params handle stall timeouts.
        response_stream = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": full_system_instruction,
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            stream=True,
        )
        finish_reason = None
        async for chunk in response_stream:
            if chunk.choices:
                if chunk.choices[0].delta and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                # Capture finish_reason from the final chunk
                if chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason
        
        # Yield finish_reason as final item
        if finish_reason:
            if finish_reason == "length":
                logger.warning(f"AI response truncated at {max_tokens} tokens (analyze_stream_with_deepseek)")
            yield f"__FINISH_REASON__{finish_reason}"
    except Exception as e:
        # Note: Streaming generator errors are raised where the generator is consumed
        logger.exception("DeepSeek stream analysis failed")
        raise HTTPException(status_code=500, detail=f"DeepSeek API Error (Stream): {str(e)}")
