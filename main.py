"""
ISO Standards AI Assistant
==========================
Entry point: wires FastAPI app, CORS middleware, and all routers.
"""

import os
import logging
import time
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.core.client import DeepSeekClient
from app.core.config import DEEPSEEK_MODEL
from app.routers import audit_lens, benchmark, chat, navigator, quiz, utils, discovery, rag

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 ISO Standards AI Assistant starting...")
    print(f"📦 DeepSeek Model: {DEEPSEEK_MODEL}")
    port = os.getenv("PORT", 8001)
    print(f"🔗 API Documentation: http://localhost:{port}/docs")
    
    yield
    
    # Shutdown
    print("🛑 Shutting down ISO Standards AI Assistant...")
    await DeepSeekClient.close()

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ISO Standards AI Assistant API",
    description="DeepSeek API-powered backend for ISO compliance management.",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def endpoint_fault_logging_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.exception(
            "Unhandled endpoint error: %s %s (%sms)",
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    if response.status_code >= 500:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.error(
            "Endpoint returned server error: %s %s -> %s (%sms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_fault_logger(request: Request, exc: StarletteHTTPException):
    if exc.status_code >= 500:
        logger.error(
            "HTTPException in endpoint: %s %s -> %s | detail=%s",
            request.method,
            request.url.path,
            exc.status_code,
            exc.detail,
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_fault_logger(request: Request, exc: Exception):
    logger.exception(
        "Unhandled exception in endpoint: %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(discovery.router)
app.include_router(navigator.router)
app.include_router(audit_lens.router)
app.include_router(benchmark.router)
app.include_router(chat.router)
app.include_router(quiz.router)
app.include_router(rag.router)
app.include_router(utils.router)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    reload = os.getenv("RELOAD", "false").lower() == "true"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload, log_level="info")
