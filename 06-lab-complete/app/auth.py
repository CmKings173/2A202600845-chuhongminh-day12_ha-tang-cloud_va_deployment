"""
Authentication — API Key (simple) + JWT (advanced)

Lab 06 dùng API Key làm primary auth.
JWT được cung cấp thêm để sinh viên tham khảo so sánh.
"""
import os
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.security.api_key import APIKeyHeader

from app.config import settings

# ─────────────────────────────────────────────────────────
# API Key Auth (primary — đơn giản, dùng trong lab)
# ─────────────────────────────────────────────────────────

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(_api_key_header)) -> str:
    """
    FastAPI dependency — kiểm tra X-API-Key header.
    Inject vào endpoint bằng: Depends(verify_api_key)
    """
    if not api_key or api_key != settings.agent_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Add header: X-API-Key: <your-key>",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key


# ─────────────────────────────────────────────────────────
# JWT Auth (advanced — tham khảo thêm)
# ─────────────────────────────────────────────────────────

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Demo users (production: lưu trong DB, hash password)
_DEMO_USERS = {
    "student": {"password": "demo123", "role": "user"},
    "admin":   {"password": "admin456", "role": "admin"},
}

_bearer = HTTPBearer(auto_error=False)


def create_access_token(username: str, role: str) -> str:
    """Tạo JWT access token với TTL 60 phút."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def authenticate_user(username: str, password: str) -> dict:
    """Xác thực username/password, trả về user info."""
    user = _DEMO_USERS.get(username)
    if not user or user["password"] != password:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"username": username, "role": user["role"]}


def verify_jwt(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> dict:
    """
    FastAPI dependency — verify JWT từ Authorization: Bearer <token>
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Bearer token required. POST /auth/token to get one.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[ALGORITHM],
        )
        return {"username": payload["sub"], "role": payload["role"]}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired. Re-login to get a new one.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=403, detail="Invalid token.")
