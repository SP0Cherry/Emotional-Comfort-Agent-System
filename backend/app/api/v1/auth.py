import hmac
import secrets
from uuid import uuid4

from fastapi import APIRouter, Request, Response

from app.config import settings
from app.db import execute, fetch_one, transaction
from app.errors import AppError
from app.schemas.requests import OTPVerify, PhoneRequest, RefreshRequest
from app.services.security import encrypt_private, issue_tokens, keyed_hash, otp_hmac, rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/otp/request")
async def request_otp(body: PhoneRequest, request: Request):
    if settings.app_env != "development":
        raise AppError(503, "SMS_NOT_CONFIGURED", "当前环境未配置短信服务。")
    await rate_limit("otp_ip", request.client.host if request.client else "unknown", 20, 600)
    await rate_limit("otp_phone", body.phone, 1, 60)
    await rate_limit("otp_phone_daily", body.phone, 20, 86400)
    phone_hash = keyed_hash(body.phone)
    challenge_id, code = uuid4(), f"{secrets.randbelow(1_000_000):06d}"
    async with transaction() as conn:
        await execute(conn, "SELECT pg_advisory_xact_lock(hashtextextended(:key,0))", {"key": phone_hash})
        await execute(conn, """UPDATE otp_challenges SET invalidated_at=now()
            WHERE phone_lookup_hash=:phone AND consumed_at IS NULL AND invalidated_at IS NULL""",
                      {"phone": phone_hash})
        await execute(conn, """INSERT INTO otp_challenges(id,phone_lookup_hash,code_hmac,expires_at)
            VALUES (:id,:phone,:code,now()+interval '5 minutes')""",
                      {"id": challenge_id, "phone": phone_hash,
                       "code": otp_hmac(challenge_id, phone_hash, code)})
    # Never returned outside development; no SMS or contact is sent by this provider.
    return {"challenge_id": challenge_id, "expires_in": 300, "development_code": code}


@router.post("/otp/verify")
async def verify_otp(body: OTPVerify, request: Request):
    await rate_limit("otp_verify_ip", request.client.host if request.client else "unknown", 60, 600)
    phone_hash = keyed_hash(body.phone)
    failure = None
    result = None
    async with transaction() as conn:
        # Same advisory lock as request prevents re-send/verification races.
        await execute(conn, "SELECT pg_advisory_xact_lock(hashtextextended(:key,0))", {"key": phone_hash})
        challenge = await fetch_one(conn, """
            SELECT *, expires_at>now() AS unexpired FROM otp_challenges
            WHERE phone_lookup_hash=:phone AND (CAST(:id AS uuid) IS NULL OR id=:id)
            ORDER BY created_at DESC LIMIT 1 FOR UPDATE
        """, {"phone": phone_hash, "id": body.challenge_id})
        if not challenge or not challenge["unexpired"] or challenge["consumed_at"] or \
                challenge["invalidated_at"] or challenge["attempts"] >= 5:
            failure = AppError(400, "OTP_INVALID", "验证码无效或已过期。")
        else:
            await execute(conn, "UPDATE otp_challenges SET attempts=attempts+1 WHERE id=:id",
                          {"id": challenge["id"]})
            if not hmac.compare_digest(challenge["code_hmac"], otp_hmac(challenge["id"], phone_hash, body.code)):
                failure = AppError(400, "OTP_INVALID", "验证码无效或已过期。")
            else:
                await execute(conn, "UPDATE otp_challenges SET consumed_at=now() WHERE id=:id",
                              {"id": challenge["id"]})
                user = await fetch_one(conn, """
                    INSERT INTO users(phone_ciphertext,phone_lookup_hash) VALUES (:cipher,:phone)
                    ON CONFLICT(phone_lookup_hash) DO UPDATE SET phone_lookup_hash=EXCLUDED.phone_lookup_hash
                    RETURNING id,nickname,status,created_at
                """, {"cipher": encrypt_private(body.phone), "phone": phone_hash})
                if user["status"] != "active":
                    failure = AppError(403, "ACCOUNT_DISABLED", "该账户当前无法登录。")
                else:
                    result = await issue_tokens(conn, user["id"], body.device_label)
                    result["user"] = user
    # Failed-attempt accounting must commit before raising an HTTP error.
    if failure:
        raise failure
    return result


@router.post("/refresh")
async def refresh(body: RefreshRequest, request: Request):
    await rate_limit("refresh_ip", request.client.host if request.client else "unknown", 120, 600)
    async with transaction() as conn:
        session = await fetch_one(conn, """
            SELECT s.* FROM refresh_sessions s JOIN users u ON u.id=s.owner_id
            WHERE s.token_hash=:hash AND s.revoked_at IS NULL AND s.expires_at>now()
            AND u.status='active' FOR UPDATE OF s
        """, {"hash": keyed_hash(body.refresh_token, "refresh")})
        if not session:
            raise AppError(401, "REFRESH_INVALID", "登录已过期，请重新登录。")
        await execute(conn, "UPDATE refresh_sessions SET revoked_at=now() WHERE id=:id", {"id": session["id"]})
        return await issue_tokens(conn, session["owner_id"], session["device_label"])


@router.post("/logout", status_code=204)
async def logout(body: RefreshRequest):
    async with transaction() as conn:
        await execute(conn, """UPDATE refresh_sessions SET revoked_at=COALESCE(revoked_at,now())
            WHERE token_hash=:hash""", {"hash": keyed_hash(body.refresh_token, "refresh")})
    return Response(status_code=204)
