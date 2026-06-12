"""
Production AI Agent — Day 12 Lab Complete

Kết hợp tất cả concepts:
  ✅ 12-Factor config (env vars)
  ✅ Structured JSON logging
  ✅ API Key authentication
  ✅ JWT auth endpoint (bonus)
  ✅ Rate limiting (sliding window)
  ✅ Cost guard (daily budget)
  ✅ Input validation (Pydantic)
  ✅ Health check + Readiness probe
  ✅ Graceful shutdown (SIGTERM)
  ✅ Security headers
  ✅ CORS
  ✅ Request logging middleware
"""
import time
import signal
import logging
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings
from app.auth import verify_api_key, authenticate_user, create_access_token
from app.rate_limiter import rate_limiter
from app.cost_guard import cost_guard
from utils.mock_llm import ask as llm_ask

# ─────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# App state
# ─────────────────────────────────────────────────────────
START_TIME = time.time()
_is_ready = False
_request_count = 0
_error_count = 0


# ─────────────────────────────────────────────────────────
# Lifespan — startup & graceful shutdown
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready

    # Startup
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "llm": "mock" if not settings.openai_api_key else "openai",
    }))
    time.sleep(0.1)  # simulate model/connection init
    _is_ready = True
    logger.info(json.dumps({"event": "ready", "port": settings.port}))

    yield  # app is running

    # Shutdown
    _is_ready = False
    logger.info(json.dumps({"event": "shutdown", "uptime": round(time.time() - START_TIME, 1)}))


# ─────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    # Ẩn /docs trên production để không lộ API schema
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


# ─────────────────────────────────────────────────────────
# Request logging + security headers middleware
# ─────────────────────────────────────────────────────────
@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1

    try:
        response: Response = await call_next(request)

        # Security headers — prevent common web attacks
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Xóa server header để không lộ thông tin platform
        if "server" in response.headers:
            del response.headers["server"]

        duration_ms = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration_ms,
        }))
        return response

    except Exception:
        _error_count += 1
        raise


# ─────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000,
                          description="Question for the AI agent")


class AskResponse(BaseModel):
    question: str
    answer: str
    model: str
    timestamp: str


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


# ─────────────────────────────────────────────────────────
# Endpoints — Info
# ─────────────────────────────────────────────────────────
@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {
            "ask":     "POST /ask        — requires X-API-Key header",
            "health":  "GET  /health     — liveness probe",
            "ready":   "GET  /ready      — readiness probe",
            "metrics": "GET  /metrics    — stats (requires X-API-Key)",
            "token":   "POST /auth/token — get JWT token (bonus)",
            "docs":    "GET  /docs       — Swagger UI (dev only)",
        },
    }


# ─────────────────────────────────────────────────────────
# Endpoints — Agent
# ─────────────────────────────────────────────────────────
@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(
    body: AskRequest,
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    """
    Send a question to the AI agent.

    **Requires:** `X-API-Key` header
    **Rate limit:** configured via RATE_LIMIT_PER_MINUTE env var
    **Cost guard:** stops when daily budget is exhausted
    """
    # 1. Rate limit — per API key (first 8 chars as bucket key)
    rate_limiter.check(api_key[:8])

    # 2. Budget check before calling LLM
    cost_guard.check()

    logger.info(json.dumps({
        "event": "agent_call",
        "q_len": len(body.question),
        "client": str(request.client.host) if request.client else "unknown",
    }))

    # 3. Call LLM (mock or real)
    answer = llm_ask(body.question)

    # 4. Record token usage (estimate: words * 1.3 ≈ tokens)
    input_tokens = max(1, int(len(body.question.split()) * 1.3))
    output_tokens = max(1, int(len(answer.split()) * 1.3))
    cost_guard.record(input_tokens, output_tokens)

    return AskResponse(
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ─────────────────────────────────────────────────────────
# Endpoints — Auth (JWT bonus)
# ─────────────────────────────────────────────────────────
@app.post("/auth/token", response_model=TokenResponse, tags=["Auth"])
def get_token(body: TokenRequest):
    """
    Lấy JWT access token bằng username/password.

    Demo users:
    - student / demo123
    - admin   / admin456
    """
    user = authenticate_user(body.username, body.password)
    token = create_access_token(user["username"], user["role"])
    return TokenResponse(access_token=token)


# ─────────────────────────────────────────────────────────
# Endpoints — Operations
# ─────────────────────────────────────────────────────────
@app.get("/health", tags=["Operations"])
def health():
    """
    Liveness probe — platform gọi định kỳ.
    Non-200 response → platform restart container.
    """
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "checks": {
            "llm": "mock" if not settings.openai_api_key else "openai",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    """
    Readiness probe — load balancer dừng gửi traffic khi 503.
    503 khi app đang khởi động hoặc shutdown.
    """
    if not _is_ready:
        raise HTTPException(status_code=503, detail="Not ready yet")
    return {"ready": True}


@app.get("/metrics", tags=["Operations"])
def metrics(api_key: str = Depends(verify_api_key)):
    """Protected metrics endpoint."""
    budget = cost_guard.stats
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "budget": budget,
    }


# ─────────────────────────────────────────────────────────
# Graceful shutdown — handle SIGTERM từ platform
# ─────────────────────────────────────────────────────────
def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal_received", "signum": signum}))
    # uvicorn handles the actual shutdown via lifespan


signal.signal(signal.SIGTERM, _handle_signal)


# ─────────────────────────────────────────────────────────
# Entry point (local dev)
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    logger.info(f"API Key: {settings.agent_api_key[:4]}****")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
