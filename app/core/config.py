import os
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------
OPENAI_MODEL: str = "gpt-5.6-luna"
OPENAI_MODEL_PRO: str = "gpt-5.6-luna"
OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

# ---------------------------------------------------------------------------
# In-memory session store
# ---------------------------------------------------------------------------
# session_id -> list of OpenAI-compatible message dicts (multi-turn history)
SESSION_STORE: Dict[str, List[Dict[str, Any]]] = {}
