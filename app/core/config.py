import os
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------
DEEPSEEK_MODEL: str = "deepseek-v4-flash"
DEEPSEEK_MODEL_PRO: str = "deepseek-v4-flash"

# ---------------------------------------------------------------------------
# In-memory session store
# ---------------------------------------------------------------------------
# session_id -> list of OpenAI-compatible message dicts (multi-turn history)
SESSION_STORE: Dict[str, List[Dict[str, Any]]] = {}
