from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.db import fetch_all, fetch_one, transaction
from app.errors import AppError, not_found
from app.schemas.requests import ConversationCreate, RunCreate
from app.services.common import decode_cursor, owned_persona, paginated
from app.services.runs import check_idempotency, create_run, lock_conversation, request_hash, run_response
from app.services.security import current_user

router = APIRouter(prefix="/conversations", tags=["conversations"])

RUN_COLUMNS = """,
    (SELECT r.id FROM chat_runs r WHERE r.conversation_id=c.id
      AND r.status IN ('queued','preparing','generating','reviewing') LIMIT 1) AS active_run_id,
    (SELECT r.id FROM chat_runs r WHERE r.conversation_id=c.id
      ORDER BY r.created_at DESC,r.id DESC LIMIT 1) AS latest_run_id
"""


@router.post("", status_code=201)
async def create_conversation(body: ConversationCreate, owner: UUID = Depends(current_user)):
    async with transaction() as conn:
        persona = await owned_persona(conn, owner, body.persona_id, lock=True, active=True)
        row = await fetch_one(conn, """INSERT INTO conversations(owner_id,persona_id,summary_context_version)
            VALUES (:owner,:persona,:version) RETURNING *""",
                              {"owner": owner, "persona": body.persona_id, "version": persona["context_version"]})
    return {**row, "active_run_id": None, "latest_run_id": None}


@router.get("")
async def list_conversations(persona_id: UUID, owner: UUID = Depends(current_user), cursor: str | None = None,
                             limit: int = Query(20, ge=1, le=50)):
    async with transaction() as conn:
        await owned_persona(conn, owner, persona_id, active=True)
        rows = await fetch_all(conn, "SELECT c.*" + RUN_COLUMNS + """ FROM conversations c
            WHERE c.owner_id=:owner AND c.persona_id=:persona AND c.mode='chat'
            AND (c.created_at,c.id)<(:cursor_time,:cursor_id)
            ORDER BY c.created_at DESC,c.id DESC LIMIT :limit""",
                               {"owner": owner, "persona": persona_id, "limit": limit + 1, **decode_cursor(cursor)})
        return paginated(rows, limit)


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: UUID, owner: UUID = Depends(current_user)):
    async with transaction() as conn:
        row = await fetch_one(conn, "SELECT c.*" + RUN_COLUMNS + """ FROM conversations c JOIN personas p
            ON p.id=c.persona_id AND p.owner_id=c.owner_id WHERE c.id=:id AND c.owner_id=:owner
            """, {"id": conversation_id, "owner": owner})
        if not row:
            raise not_found()
        await owned_persona(conn, owner, row["persona_id"], active=True)
    return row


@router.get("/{conversation_id}/messages")
async def messages(conversation_id: UUID, owner: UUID = Depends(current_user),
                   before_seq: int | None = Query(None, gt=0), limit: int = Query(50, ge=1, le=50)):
    async with transaction() as conn:
        conversation = await fetch_one(conn, """SELECT c.persona_id FROM conversations c JOIN personas p
            ON p.id=c.persona_id AND p.owner_id=c.owner_id WHERE c.id=:id AND c.owner_id=:owner""",
                                       {"id": conversation_id, "owner": owner})
        if not conversation:
            raise not_found()
        await owned_persona(conn, owner, conversation["persona_id"], active=True)
        rows = await fetch_all(conn, """SELECT m.*,
            (SELECT r.id FROM chat_runs r WHERE r.assistant_message_id=m.id LIMIT 1) AS run_id
            FROM messages m WHERE m.conversation_id=:id AND m.owner_id=:owner AND m.seq<:before
            ORDER BY m.seq DESC LIMIT :limit""",
                               {"id": conversation_id, "owner": owner, "before": before_seq or 9223372036854775807,
                                "limit": limit + 1})
    more = len(rows) > limit
    items = list(reversed(rows[:limit]))
    return {"items": items, "next_before_seq": items[0]["seq"] if more else None}


@router.post("/{conversation_id}/runs", status_code=202)
async def submit_run(conversation_id: UUID, body: RunCreate, owner: UUID = Depends(current_user)):
    fingerprint = request_hash({"conversation_id": conversation_id, "text": body.text})
    async with transaction() as conn:
        persona, conversation = await lock_conversation(conn, owner, conversation_id)
        existing = await check_idempotency(conn, owner, body.client_message_id, fingerprint)
        if existing:
            return JSONResponse(jsonable_encoder(run_response(existing)), status_code=200)
        if conversation["mode"] != "chat":
            raise AppError(409, "PREVIEW_READ_ONLY", "预览会话不能继续聊天，请新建普通会话。")
        return run_response(await create_run(conn, owner, persona, conversation, body.client_message_id,
                                             body.text, fingerprint))
