from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.config import settings
from app.db import execute, fetch_all, fetch_one, transaction
from app.errors import AppError, not_found
from app.schemas.requests import MemoryEdit, RevisionRequest
from app.services.common import decode_cursor, owned_persona, paginated
from app.services.security import current_user

router = APIRouter(prefix="/memories", tags=["memories"])

MEMORY_COLUMNS = "id,owner_id,persona_id,content,category,status,revision,confirmed_at,valid_until,created_at,updated_at"


async def lock_memory(conn, owner, memory_id):
    raw = await fetch_one(conn, "SELECT persona_id FROM memories WHERE id=:id AND owner_id=:owner",
                          {"id": memory_id, "owner": owner})
    if not raw:
        raise not_found()
    await owned_persona(conn, owner, raw["persona_id"], lock=True, active=True)
    await fetch_all(conn, """SELECT id FROM conversations WHERE owner_id=:owner AND persona_id=:id
        ORDER BY id FOR UPDATE""", {"owner": owner, "id": raw["persona_id"]})
    await fetch_all(conn, """SELECT j.id FROM jobs j WHERE j.owner_id=:owner AND j.kind='summarize'
        AND j.state IN ('queued','leased') AND j.target_id IN
            (SELECT id FROM chat_runs WHERE owner_id=:owner AND persona_id=:persona)
        ORDER BY j.id FOR UPDATE""", {"owner": owner, "persona": raw["persona_id"]})
    row = await fetch_one(conn, f"SELECT {MEMORY_COLUMNS} FROM memories WHERE id=:id AND owner_id=:owner FOR UPDATE",
                          {"id": memory_id, "owner": owner})
    if not row:
        raise not_found()
    return row


def check_revision(memory, revision):
    if memory["revision"] != revision:
        raise AppError(409, "VERSION_CONFLICT", "记忆已更新，请刷新后重试。")


async def invalidate_summaries(conn, owner, persona_id):
    await execute(conn, """UPDATE jobs SET state='completed',error_code='MEMORY_CHANGED',
        lease_until=NULL,lease_token=NULL,updated_at=now() WHERE owner_id=:owner AND kind='summarize'
        AND state IN ('queued','leased') AND target_id IN
            (SELECT id FROM chat_runs WHERE owner_id=:owner AND persona_id=:persona)""",
                  {"owner": owner, "persona": persona_id})
    await execute(conn, """UPDATE conversations SET summary='',summary_until_seq=0
        WHERE owner_id=:owner AND persona_id=:persona""", {"owner": owner, "persona": persona_id})


async def view_memory(conn, row):
    sources = await fetch_all(conn, """SELECT message_id FROM memory_sources WHERE owner_id=:owner
        AND memory_id=:id ORDER BY message_id""", {"owner": row["owner_id"], "id": row["id"]})
    return {**row, "source_message_ids": [source["message_id"] for source in sources]}


@router.get("")
async def memories(persona_id: UUID, owner: UUID = Depends(current_user), cursor: str | None = None,
                   status: Literal["candidate", "indexing", "active", "rejected", "superseded"] | None = None,
                   limit: int = Query(20, ge=1, le=50)):
    async with transaction() as conn:
        await owned_persona(conn, owner, persona_id, active=True)
        rows = await fetch_all(conn, f"""SELECT {MEMORY_COLUMNS} FROM memories WHERE owner_id=:owner
            AND persona_id=:persona AND ((CAST(:status AS text) IS NULL AND status IN ('candidate','indexing','active'))
                OR status=:status)
            AND (created_at,id)<(:cursor_time,:cursor_id) ORDER BY created_at DESC,id DESC LIMIT :limit""",
                               {"owner": owner, "persona": persona_id, "status": status,
                                "limit": limit + 1, **decode_cursor(cursor)})
        result = paginated(rows, limit)
        result["items"] = [await view_memory(conn, row) for row in result["items"]]
        return result


@router.post("/{memory_id}/confirm", status_code=202)
async def confirm(memory_id: UUID, body: RevisionRequest, owner: UUID = Depends(current_user)):
    async with transaction() as conn:
        memory = await lock_memory(conn, owner, memory_id)
        check_revision(memory, body.revision)
        if memory["status"] not in {"candidate", "indexing", "active"}:
            raise AppError(409, "MEMORY_NOT_CONFIRMABLE", "该记忆当前不能确认。")
        if memory["status"] == "active":
            return await view_memory(conn, memory)
        row = await fetch_one(conn, f"""UPDATE memories SET status='indexing',confirmed_at=COALESCE(confirmed_at,now()),
            updated_at=now() WHERE id=:id AND owner_id=:owner RETURNING {MEMORY_COLUMNS}""",
                              {"id": memory_id, "owner": owner})
        await execute(conn, """INSERT INTO jobs(owner_id,kind,target_id,target_version,dedup_key,max_attempts)
            VALUES (:owner,'embed_memory',:id,:revision,:dedup,3) ON CONFLICT(dedup_key) DO NOTHING""",
                      {"owner": owner, "id": memory_id, "revision": body.revision,
                       "dedup": f"embed:{memory_id}:{body.revision}:{settings.embedding_model}"})
        # Confirmed facts take precedence over old summaries; discard them for safe regeneration.
        await invalidate_summaries(conn, owner, memory["persona_id"])
        return await view_memory(conn, row)


@router.patch("/{memory_id}")
async def edit(memory_id: UUID, body: MemoryEdit, owner: UUID = Depends(current_user)):
    async with transaction() as conn:
        memory = await lock_memory(conn, owner, memory_id)
        check_revision(memory, body.revision)
        if memory["status"] in {"rejected", "superseded"}:
            raise AppError(409, "MEMORY_NOT_EDITABLE", "该记忆当前不能修改。")
        row = await fetch_one(conn, f"""UPDATE memories SET content=:content,revision=revision+1,
            status='candidate',embedding=NULL,embedding_model=NULL,embedding_revision=NULL,
            confirmed_at=NULL,updated_at=now() WHERE id=:id AND owner_id=:owner RETURNING {MEMORY_COLUMNS}""",
                              {"id": memory_id, "owner": owner, "content": body.content})
        await invalidate_summaries(conn, owner, memory["persona_id"])
        return await view_memory(conn, row)


@router.post("/{memory_id}/reject")
async def reject(memory_id: UUID, body: RevisionRequest, owner: UUID = Depends(current_user)):
    async with transaction() as conn:
        memory = await lock_memory(conn, owner, memory_id)
        check_revision(memory, body.revision)
        if memory["status"] not in {"candidate", "rejected"}:
            raise AppError(409, "MEMORY_NOT_REJECTABLE", "只能拒绝待确认的记忆。")
        row = await fetch_one(conn, f"""UPDATE memories SET status='rejected',embedding=NULL,
            embedding_model=NULL,embedding_revision=NULL,updated_at=now()
            WHERE id=:id AND owner_id=:owner RETURNING {MEMORY_COLUMNS}""", {"id": memory_id, "owner": owner})
        return await view_memory(conn, row)


@router.delete("/{memory_id}", status_code=204)
async def remove(memory_id: UUID, owner: UUID = Depends(current_user)):
    async with transaction() as conn:
        memory = await lock_memory(conn, owner, memory_id)
        await execute(conn, """UPDATE messages SET memory_blocked=true,updated_at=now()
            WHERE owner_id=:owner AND id IN (SELECT message_id FROM memory_sources
                WHERE owner_id=:owner AND memory_id=:id)""", {"owner": owner, "id": memory_id})
        await execute(conn, "DELETE FROM memories WHERE id=:id AND owner_id=:owner", {"id": memory_id, "owner": owner})
        await invalidate_summaries(conn, owner, memory["persona_id"])
    return Response(status_code=204)
