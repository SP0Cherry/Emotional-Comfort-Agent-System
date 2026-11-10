import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from cryptography.fernet import Fernet
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.db import execute, fetch_one, transaction
from app.errors import AppError

bearer = HTTPBearer(auto_error=False)


def keyed_hash(value: str, purpose: str = "phone") -> str:
    return hmac.new(settings.secret_key.encode(), f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def encrypt_private(value: str) -> bytes:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.phone_encryption_key.encode()).digest())
    return Fernet(key).encrypt(value.encode())


def decrypt_private(value: bytes) -> str:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.phone_encryption_key.encode()).digest())
    return Fernet(key).decrypt(value).decode()


def otp_hmac(challenge_id: UUID, phone_hash: str, code: str):
    return keyed_hash(f"{challenge_id}:{phone_hash}:{code}", "otp")


async def rate_limit(scope: str, subject: str, limit: int, seconds: int):
    now = datetime.now(UTC)
    bucket = datetime.fromtimestamp(int(now.timestamp()) // seconds * seconds, UTC)
    async with transaction() as conn:
        row = await fetch_one(conn, """
            INSERT INTO rate_limit_counters(scope,subject_hash,bucket_start,count,expires_at)
            VALUES (:scope,:subject,:bucket,1,:expires)
            ON CONFLICT(scope,subject_hash,bucket_start) DO UPDATE
            SET count=rate_limit_counters.count+1 RETURNING count
        """, {"scope": scope, "subject": keyed_hash(subject, "rate"), "bucket": bucket,
              "expires": bucket + timedelta(seconds=seconds * 2)})
    if row["count"] > limit:
        raise AppError(429, "RATE_LIMITED", "操作过于频繁，请稍后重试。")


async def issue_tokens(conn, owner_id: UUID, device_label: str = ""):
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.access_token_minutes)
    access = jwt.encode({"sub": str(owner_id), "iat": now, "exp": expires,
                         "jti": str(uuid4()), "type": "access", "iss": "companion-agent",
                         "aud": "companion-client"}, settings.secret_key, algorithm="HS256")
    refresh = secrets.token_urlsafe(48)
    await execute(conn, """
        INSERT INTO refresh_sessions(owner_id,token_hash,device_label,expires_at)
        VALUES (:owner,:hash,:label,:expires)
    """, {"owner": owner_id, "hash": keyed_hash(refresh, "refresh"), "label": device_label,
          "expires": now + timedelta(days=settings.refresh_token_days)})
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer",
            "expires_in": settings.access_token_minutes * 60}


async def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> UUID:
    if credentials is None:
        raise AppError(401, "UNAUTHORIZED", "请先登录。")
    try:
        claims = jwt.decode(credentials.credentials, settings.secret_key, algorithms=["HS256"],
                            issuer="companion-agent", audience="companion-client",
                            options={"require": ["exp", "iat", "sub", "jti", "type"]})
        if claims["type"] != "access":
            raise ValueError("Wrong token type")
        owner_id = UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise AppError(401, "UNAUTHORIZED", "登录已过期，请重新登录。") from None
    async with transaction() as conn:
        user = await fetch_one(conn, "SELECT id FROM users WHERE id=:owner AND status='active'",
                               {"owner": owner_id})
    if not user:
        raise AppError(401, "UNAUTHORIZED", "登录已失效。")
    return owner_id
