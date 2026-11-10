from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import execute, fetch_all, fetch_one, transaction
from app.errors import AppError, not_found
from app.schemas.requests import PersonaCreate, PersonaPatch, PreviewCreate, ResetRequest
from app.services.common import decode_cursor, json_dump, owned_persona, paginated
from app.services.security import current_user

router = APIRouter(prefix="/personas", tags=["personas"])


async def validate_avatar(conn, owner, asset_id):
    if asset_id is None:
        return
    asset = await fetch_one(conn, """SELECT purpose,status FROM assets WHERE id=:id AND owner_id=:owner
        FOR UPDATE""", {"id": asset_id, "owner": owner})
    if not asset:
        raise not_found()
    if asset["purpose"] != "avatar" or asset["status"] != "ready":
        raise AppError(400, "INVALID_AVATAR", "头像不存在或尚未处理完成。")


async def persona_view(conn, persona):
    data = dict(persona)
    data["style"] = data.pop("style_json")
    examples = await fetch_all(conn, """SELECT sample_text FROM persona_examples
        WHERE persona_id=:id AND owner_id=:owner AND approved ORDER BY created_at,id""",
                               {"id": data["id"], "owner": data["owner_id"]})
    data["examples"] = [item["sample_text"] for item in examples]
    data["reset_operation_id"] = None
    if data["status"] == "resetting":
        operation = await fetch_one(conn, "SELECT id FROM jobs WHERE owner_id=:owner AND dedup_key=:dedup",
                                    {"owner": data["owner_id"],
                                     "dedup": f"purge:persona:{data['id']}:{data['context_version']}"})
        if operation:
            data["reset_operation_id"] = operation["id"]
    return data


async def save_examples(conn, owner, persona_id, examples):
    await execute(conn, "DELETE FROM persona_examples WHERE owner_id=:owner AND persona_id=:id",
                  {"owner": owner, "id": persona_id})
    for example in examples:
        await execute(conn, """INSERT INTO persona_examples(owner_id,persona_id,sample_text,approved)
            VALUES (:owner,:id,:text,true)""", {"owner": owner, "id": persona_id, "text": example})


@router.post("", status_code=201)
async def create_persona(body: PersonaCreate, owner: UUID = Depends(current_user)):
    async with transaction() as conn:
        # Serialize quota checks across requests from one account.
        await execute(conn, "SELECT id FROM users WHERE id=:id FOR UPDATE", {"id": owner})
        count = await fetch_one(conn, "SELECT count(*) AS n FROM personas WHERE owner_id=:owner",
                                {"owner": owner})
        if count["n"] >= settings.max_personas:
            raise AppError(409, "PERSONA_LIMIT", "人物数量已达到当前额度。")
        await validate_avatar(conn, owner, body.avatar_asset_id)
        persona = await fetch_one(conn, """
            INSERT INTO personas(owner_id,display_name,avatar_asset_id,relationship_reference,style_json)
            VALUES (:owner,:name,:avatar,:relationship,CAST(:style AS jsonb)) RETURNING *
        """, {"owner": owner, "name": body.display_name, "avatar": body.avatar_asset_id,
              "relationship": body.relationship_reference, "style": json_dump(body.style.model_dump())})
        await save_examples(conn, owner, persona["id"], body.examples)
        return await persona_view(conn, persona)


@router.get("")
async def list_personas(owner: UUID = Depends(current_user), cursor: str | None = None,
                        limit: int = Query(20, ge=1, le=50)):
    async with transaction() as conn:
        rows = await fetch_all(conn, """SELECT * FROM personas WHERE owner_id=:owner
            AND (created_at,id)<(:cursor_time,:cursor_id) ORDER BY created_at DESC,id DESC LIMIT :limit""",
                               {"owner": owner, "limit": limit + 1, **decode_cursor(cursor)})
        result = paginated(rows, limit)
        result["items"] = [await persona_view(conn, row) for row in result["items"]]
        return result


@router.get("/{persona_id}")
async def get_persona(persona_id: UUID, owner: UUID = Depends(current_user)):
    async with transaction() as conn:
        return await persona_view(conn, await owned_persona(conn, owner, persona_id))


@router.patch("/{persona_id}")
async def update_persona(persona_id: UUID, body: PersonaPatch, owner: UUID = Depends(current_user)):
    async with transaction() as conn:
        old = await owned_persona(conn, owner, persona_id, lock=True, active=True)
        if old["style_version"] != body.style_version:
            raise AppError(409, "VERSION_CONFLICT", "人物资料已更新，请刷新后重试。")
        values = body.model_dump(exclude_unset=True)
        # Explicit null is supported only for unbinding an avatar.
        if any(values.get(key, "present") is None for key in
               ("display_name", "relationship_reference", "style", "examples")):
            raise AppError(422, "INVALID_PERSONA", "人物字段不能为空。")
        if "avatar_asset_id" in values:
            await validate_avatar(conn, owner, body.avatar_asset_id)
        data = {"id": persona_id, "owner": owner,
                "name": values.get("display_name", old["display_name"]),
                "avatar": values.get("avatar_asset_id", old["avatar_asset_id"]),
                "relationship": values.get("relationship_reference", old["relationship_reference"]),
                "style": json_dump(values.get("style", old["style_json"]))}
        new = await fetch_one(conn, """UPDATE personas SET display_name=:name,avatar_asset_id=:avatar,
            relationship_reference=:relationship,style_json=CAST(:style AS jsonb),
            style_version=style_version+1,updated_at=now() WHERE id=:id AND owner_id=:owner RETURNING *""", data)
        if "examples" in values:
            await save_examples(conn, owner, persona_id, body.examples)
        return await persona_view(conn, new)


@router.post("/{persona_id}/preview", status_code=202)
async def preview(persona_id: UUID, body: PreviewCreate, owner: UUID = Depends(current_user)):
    from app.services.runs import create_run, request_hash, run_response

    fingerprint = request_hash({"operation": "preview", "persona_id": persona_id,
                                "sample_question": body.sample_question})
    async with transaction() as conn:
        persona = await owned_persona(conn, owner, persona_id, lock=True, active=True)
        existing = await fetch_one(conn, "SELECT * FROM chat_runs WHERE owner_id=:owner AND client_message_id=:client",
                                   {"owner": owner, "client": body.client_message_id})
        if existing:
            if existing["request_hash"] != fingerprint:
                raise AppError(409, "IDEMPOTENCY_CONFLICT", "发送标识已用于其他请求。")
            return JSONResponse(run_response(existing), status_code=200)
        conversation = await fetch_one(conn, """INSERT INTO conversations(owner_id,persona_id,mode,
            summary_context_version) VALUES (:owner,:persona,'preview',:version) RETURNING *""",
                                       {"owner": owner, "persona": persona_id, "version": persona["context_version"]})
        run = await create_run(conn, owner, persona, conversation, body.client_message_id,
                               body.sample_question, fingerprint)
        return run_response(run)


@router.post("/{persona_id}/reset-context", status_code=202)
async def reset_context(persona_id: UUID, body: ResetRequest, owner: UUID = Depends(current_user)):
    from app.services.runs import append_event

    async with transaction() as conn:
        persona = await owned_persona(conn, owner, persona_id, lock=True)
        if persona["status"] == "resetting":
            job = await fetch_one(conn, """SELECT id,state FROM jobs WHERE owner_id=:owner AND
                dedup_key=:dedup""", {"owner": owner,
                                       "dedup": f"purge:persona:{persona_id}:{persona['context_version']}"})
            if job:
                return {"operation_id": job["id"], "status": job["state"]}
        if persona["status"] != "active":
            raise AppError(409, "PERSONA_UNAVAILABLE", "人物资料正在处理，请稍后重试。")
        await fetch_all(conn, """SELECT id FROM conversations WHERE owner_id=:owner AND persona_id=:id
            ORDER BY id FOR UPDATE""", {"owner": owner, "id": persona_id})
        await execute(conn, """UPDATE conversations SET summary='',summary_until_seq=0
            WHERE owner_id=:owner AND persona_id=:id""", {"owner": owner, "id": persona_id})
        # Fence every pending background writer, including extraction/embedding/summary.
        pending_jobs = await fetch_all(conn, """SELECT j.id FROM jobs j WHERE j.owner_id=:owner
            AND j.state IN ('queued','leased') AND (
                j.target_id=:id OR
                j.target_id IN (SELECT id FROM chat_runs WHERE owner_id=:owner AND persona_id=:id) OR
                j.target_id IN (SELECT id FROM memories WHERE owner_id=:owner AND persona_id=:id) OR
                j.target_id IN (SELECT id FROM conversations WHERE owner_id=:owner AND persona_id=:id) OR
                j.target_id IN (SELECT s.id FROM safety_events s JOIN chat_runs r ON r.id=s.run_id
                    WHERE s.owner_id=:owner AND r.persona_id=:id)
            ) ORDER BY j.id FOR UPDATE""", {"owner": owner, "id": persona_id})
        for item in pending_jobs:
            await execute(conn, """UPDATE jobs SET state='completed',error_code='CONTEXT_RESET',
                lease_until=NULL,lease_token=NULL,updated_at=now() WHERE id=:id""", {"id": item["id"]})
        runs = await fetch_all(conn, """SELECT * FROM chat_runs WHERE owner_id=:owner AND persona_id=:id
            AND status IN ('queued','preparing','generating','reviewing') ORDER BY id FOR UPDATE""",
                               {"owner": owner, "id": persona_id})
        for run in runs:
            await execute(conn, """UPDATE chat_runs SET status='cancelled',error_code='CONTEXT_RESET',
                cancel_requested_at=now(),finished_at=now(),updated_at=now() WHERE id=:id""", {"id": run["id"]})
            await execute(conn, "UPDATE messages SET status='cancelled',updated_at=now() WHERE id=:id",
                          {"id": run["assistant_message_id"]})
            await append_event(conn, run["id"], "run.cancelled", {"status": "cancelled", "error_code": "CONTEXT_RESET"})
        version = persona["context_version"] + 1
        await execute(conn, """UPDATE personas SET status='resetting',context_version=:version,
            updated_at=now() WHERE id=:id AND owner_id=:owner""", {"id": persona_id, "owner": owner, "version": version})
        operation = uuid4()
        await execute(conn, """INSERT INTO jobs(id,owner_id,kind,target_id,target_version,dedup_key,max_attempts)
            VALUES (:job,:owner,'purge_data',:id,:version,:dedup,3)""",
                      {"job": operation, "owner": owner, "id": persona_id, "version": version,
                       "dedup": f"purge:persona:{persona_id}:{version}"})
        return {"operation_id": operation, "status": "queued", "context_version": version}


@router.get("/{persona_id}/export")
async def export_persona(persona_id: UUID, owner: UUID = Depends(current_user)):
    from fastapi.encoders import jsonable_encoder

    async with transaction() as conn:
        # A shared persona lock serializes a coherent export against reset and writers.
        persona = await owned_persona(conn, owner, persona_id, lock=True, active=True)
        conversations = await fetch_all(conn, """SELECT * FROM conversations WHERE owner_id=:owner
            AND persona_id=:id ORDER BY created_at,id""", {"owner": owner, "id": persona_id})
        messages = await fetch_all(conn, """SELECT * FROM messages WHERE owner_id=:owner AND persona_id=:id
            ORDER BY conversation_id,seq""", {"owner": owner, "id": persona_id})
        memories = await fetch_all(conn, """SELECT id,content,category,status,revision,confirmed_at,created_at,
            updated_at FROM memories WHERE owner_id=:owner AND persona_id=:id ORDER BY created_at,id""",
                                   {"owner": owner, "id": persona_id})
        sources = await fetch_all(conn, """SELECT memory_id,message_id FROM memory_sources
            WHERE owner_id=:owner AND persona_id=:id ORDER BY memory_id,message_id""", {"owner": owner, "id": persona_id})
        return JSONResponse(jsonable_encoder({"format_version": 1, "persona": await persona_view(conn, persona),
                            "conversations": conversations, "messages": messages,
                            "memories": memories, "memory_sources": sources}),
                            headers={"Content-Disposition": f'attachment; filename="persona-{persona_id}.json"',
                                     "Cache-Control": "no-store"})
