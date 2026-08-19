import os
from typing import Optional

from fastapi import HTTPException
from openai import AsyncOpenAI

DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class DeepSeekClient:
    """Singleton DeepSeek client manager."""

    _async_client: Optional[AsyncOpenAI] = None

    @classmethod
    def get_async_client(cls) -> AsyncOpenAI:
        if cls._async_client is None:
            api_key = os.getenv("DEEPSEEK_API_KEY")
            timeout_seconds = float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "600"))
            if not api_key:
                raise HTTPException(
                    status_code=500,
                    detail="DEEPSEEK_API_KEY environment variable not set. Please check your .env file.",
                )
            cls._async_client = AsyncOpenAI(
                api_key=api_key,
                base_url=DEEPSEEK_BASE_URL,
                timeout=timeout_seconds,
                max_retries=1,
            )
        return cls._async_client

    @classmethod
    async def close(cls) -> None:
        if cls._async_client:
            try:
                await cls._async_client.close()
            except Exception:
                pass
            cls._async_client = None
