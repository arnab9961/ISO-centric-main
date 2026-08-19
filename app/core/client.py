import os
from typing import Optional

from fastapi import HTTPException
from openai import AsyncOpenAI


class OpenAIClient:
    """Singleton OpenAI client manager."""

    _async_client: Optional[AsyncOpenAI] = None

    @classmethod
    def get_async_client(cls) -> AsyncOpenAI:
        if cls._async_client is None:
            api_key = os.getenv("OPENAI_API_KEY")
            timeout_seconds = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "600"))
            if not api_key:
                raise HTTPException(
                    status_code=500,
                    detail="OPENAI_API_KEY environment variable not set. Please check your .env file.",
                )
            cls._async_client = AsyncOpenAI(
                api_key=api_key,
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
