from __future__ import annotations

import json
from typing import Any, Dict


def is_truncated(finish_reason: str) -> bool:
    """Check if AI response was truncated due to token limit."""
    return finish_reason == "length"


def get_json_wrap_message() -> str:
    """Standard warning message for truncated JSON responses."""
    return "⚠️ Response exceeded token limit and was truncated. Some data may be incomplete."


def get_text_wrap_message() -> str:
    """Standard note appended to truncated text responses."""
    return "\n\n[Note: Response was truncated due to length limits. The content above may be incomplete.]"


def attempt_json_repair(content: str) -> Dict[str, Any]:
    """
    Attempt to repair truncated JSON by closing unclosed structures.
    Raises ValueError if repair is not possible.
    """
    if not content or not content.strip():
        raise ValueError("Empty content cannot be repaired")
    
    content = content.strip()
    
    # Try parsing as-is first
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    
    # Count unclosed brackets and braces
    open_braces = content.count("{") - content.count("}")
    open_brackets = content.count("[") - content.count("]")
    
    # Attempt repair by closing structures
    repaired = content
    
    # Remove trailing incomplete string or key-value pair
    if repaired.endswith(','):
        repaired = repaired.rstrip(',').rstrip()
    elif repaired.rstrip().endswith('"'):
        # Check if we have an incomplete string - remove back to last complete comma or opening brace
        last_comma = repaired.rfind(',')
        last_open_brace = repaired.rfind('{')
        last_open_bracket = repaired.rfind('[')
        last_valid = max(last_comma, last_open_brace, last_open_bracket)
        if last_valid > 0:
            repaired = repaired[:last_valid + 1].rstrip()
            if repaired.endswith(','):
                repaired = repaired[:-1].rstrip()
    
    # Close unclosed structures
    if open_brackets > 0:
        repaired += "]" * open_brackets
    if open_braces > 0:
        repaired += "}" * open_braces
    
    # Try parsing repaired version
    try:
        parsed = json.loads(repaired)
        return parsed
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not repair truncated JSON: {str(e)}")
