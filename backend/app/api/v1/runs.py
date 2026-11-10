import asyncio
import json
import time
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import settings
from app.db import execute, fetch_all, fetch_one, transaction
from app.errors import AppError, not_found
from app.schemas.requests import RetryRequest
from app.services.common import owned_persona
from app.services.runs import (TERMINAL, append_event, check_idempotency, create_run, lock_run,
                               request_hash, run_response)
from app.services.security import current_user

router = APIRouter(prefix="/runs", tags=["runs"])


async def read_run(conn, owner, run_id):
    row = await fetch_one(conn, """SELECT r.* FROM chat_runs r JOIN personas p ON p.id=r.persona_id
        AND p.owner_id=r.owner_id WHERE r.id=:id AND r.owner_id=:owner""",
                          {"id": run_id, "owner": owner})
    if not row:
        raise not_found()
    await owned_persona(conn, owner, row["persona_id"], active=True)
    return row


@router.get("/{run_id}")
async def get_run(run_id: UUID, owner: UUID = Depends(current_user)):
    async with transaction() as conn:
        row = await read_run(conn, owner, run_id)
        message = await fetch_one(conn, "SELECT * FROM messages WHERE id=:id AND owner_id=:owner",
                                  {"id": row["assistant_message_id"], "owner": owner})
    return {**run_response(row), "last_event_seq": row["next_event_seq"] - 1,
            "assistant_message": message, "usage": row["usage_json"],
            "created_at": row["created_at"], "finished_at": row["finished_at"]}


@router.get("/{run_id}/events")
async def events(run_id: UUID, request: Request, owner: UUID = Depends(current_user),
                 after_seq: int | None = Query(None, ge=0),
                 last_event_id: str | None = Header(None, alias="Last-Event-ID")):
    if after_seq is None:
        try:
            after_seq = int(last_event_id) if last_event_id is not None else 0
            if after_seq < 0:
                raise ValueError("negative cursor")
        except ValueError:
            raise AppError(400, "INVALID_EVENT_CURSOR", "事件序号无效。") from None
    async with transaction() as conn:
        run = await read_run(conn, owner, run_id)
        bounds = await fetch_one(conn, "SELECT min(seq) AS min_seq,max(seq) AS max_seq FROM run_events WHERE run_id=:id",
                                 {"id": run_id})
    if after_seq > run["next_event_seq"] - 1:
        raise AppError(400, "INVALID_EVENT_CURSOR", "事件序号超出当前范围。")
    if (bounds["min_seq"] is None and run["next_event_seq"] > 1) or \
            (bounds["min_seq"] is not None and after_seq < bounds["min_seq"] - 1):
        raise AppError(410, "EVENTS_EXPIRED", "事件已过期，请读取当前消息。")

    async def stream():
        cursor, heartbeat = after_seq, time.monotonic()
        while not await request.is_disconnected():
            # Each poll returns its pooled connection before waiting or yielding network data.
            async with transaction() as conn:
                current = await fetch_one(conn, """SELECT r.status,p.status AS persona_status FROM chat_runs r
                    JOIN personas p ON p.id=r.persona_id AND p.owner_id=r.owner_id
                    WHERE r.id=:id AND r.owner_id=:owner FOR SHARE OF p""", {"id": run_id, "owner": owner})
                if not current or current["persona_status"] != "active":
                    break
                batch = await fetch_all(conn, """SELECT seq,event_type,payload FROM run_events
                    WHERE run_id=:id AND seq>:after ORDER BY seq LIMIT 100""", {"id": run_id, "after": cursor})
            for event in batch:
                payload = {**event["payload"], "run_id": str(run_id), "seq": event["seq"]}
                yield f"id: {event['seq']}\nevent: {event['event_type']}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                cursor = event["seq"]
            if current["status"] in TERMINAL and len(batch) < 100:
                break
            if time.monotonic() - heartbeat >= 15:
                yield ": ping\n\n"
                heartbeat = time.monotonic()
            await asyncio.sleep(settings.sse_poll_seconds)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{run_id}/cancel")
async def cancel(run_id: UUID, owner: UUID = Depends(current_user)):
    async with transaction() as conn:
        persona, conversation, jobs, run = await lock_run(conn, owner, run_id)
        if run["status"] in TERMINAL:
            return run_response(run)
        if run["status"] == "queued":
            for job in jobs:
                await execute(conn, """UPDATE jobs SET state='completed',lease_until=NULL,lease_token=NULL,
                    error_code='USER_CANCELLED',updated_at=now() WHERE id=:id""", {"id": job["id"]})
            run = await fetch_one(conn, """UPDATE chat_runs SET status='cancelled',cancel_requested_at=now(),
                finished_at=now(),updated_at=now() WHERE id=:id RETURNING *""", {"id": run_id})
            await execute(conn, "UPDATE messages SET status='cancelled',updated_at=now() WHERE id=:id",
                          {"id": run["assistant_message_id"]})
            await append_event(conn, run_id, "run.cancelled", {"status": "cancelled"})
            return run_response(run)
        run = await fetch_one(conn, """UPDATE chat_runs SET cancel_requested_at=COALESCE(cancel_requested_at,now()),
            updated_at=now() WHERE id=:id RETURNING *""", {"id": run_id})
        return JSONResponse(jsonable_encoder(run_response(run)), status_code=202)


@router.post("/{run_id}/retry", status_code=202)
async def retry(run_id: UUID, body: RetryRequest, owner: UUID = Depends(current_user)):
    fingerprint = request_hash({"operation": "retry", "run_id": run_id})
    async with transaction() as conn:
        persona, conversation, jobs, original = await lock_run(conn, owner, run_id)
        if persona["status"] != "active":
            raise AppError(409, "PERSONA_UNAVAILABLE", "人物资料正在处理，请稍后重试。")
        existing = await check_idempotency(conn, owner, body.client_message_id, fingerprint)
        if existing:
            return JSONResponse(jsonable_encoder(run_response(existing)), status_code=200)
        latest = await fetch_one(conn, """SELECT id FROM chat_runs WHERE conversation_id=:id
            AND owner_id=:owner ORDER BY created_at DESC,id DESC LIMIT 1""",
                                 {"id": conversation["id"], "owner": owner})
        newer_input = await fetch_one(conn, """SELECT id FROM messages WHERE conversation_id=:conversation
            AND owner_id=:owner AND role='user' AND seq>(SELECT seq FROM messages WHERE id=:user) LIMIT 1""",
                                      {"conversation": conversation["id"], "owner": owner, "user": original["user_message_id"]})
        if original["status"] not in {"failed", "cancelled", "interrupted"} or \
                latest["id"] != run_id or newer_input:
            raise AppError(409, "RETRY_NOT_ALLOWED", "只能重新生成最近一次失败或已停止的回复。")
        result = await create_run(conn, owner, persona, conversation, body.client_message_id, "", fingerprint,
                                  retry_of=run_id, reuse_user=original["user_message_id"])
        return run_response(result)
