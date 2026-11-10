import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.config import settings
from app.db import execute, fetch_all, fetch_one
from app.errors import AppError, not_found
from app.services.common import json_dump, owned_persona
from app.services.security import keyed_hash

ACTIVE = {"queued", "preparing", "generating", "reviewing"}
TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


def request_hash(payload):
    return hashlib.sha256(json_dump(payload).encode()).hexdigest()


def run_response(run):
    return {"run_id": str(run["id"]), "status": run["status"],
            "conversation_id": str(run["conversation_id"]),
            "user_message_id": str(run["user_message_id"]),
            "assistant_message_id": str(run["assistant_message_id"]),
            "events_url": f"/v1/runs/{run['id']}/events",
            "error_code": run.get("error_code"),
            "cancel_requested": run.get("cancel_requested_at") is not None}


async def append_event(conn, run_id, event_type, payload):
    row = await fetch_one(conn, """UPDATE chat_runs SET next_event_seq=next_event_seq+1
        WHERE id=:id RETURNING next_event_seq-1 AS seq""", {"id": run_id})
    payload = {**payload, "run_id": str(run_id), "seq": row["seq"]}
    await execute(conn, """INSERT INTO run_events(run_id,seq,event_type,payload)
        VALUES (:id,:seq,:type,CAST(:payload AS jsonb))""",
                  {"id": run_id, "seq": row["seq"], "type": event_type, "payload": json_dump(payload)})


async def check_idempotency(conn, owner, client_id, fingerprint):
    existing = await fetch_one(conn, "SELECT * FROM chat_runs WHERE owner_id=:owner AND client_message_id=:client",
                               {"owner": owner, "client": client_id})
    if existing and existing["request_hash"] != fingerprint:
        raise AppError(409, "IDEMPOTENCY_CONFLICT", "发送标识已用于其他请求。")
    return existing


async def run_quota(conn, owner, preview):
    now = datetime.now(UTC)
    period = 3600 if preview else 86400
    bucket = datetime.fromtimestamp(int(now.timestamp()) // period * period, UTC)
    count = await fetch_one(conn, """
        INSERT INTO rate_limit_counters(scope,subject_hash,bucket_start,count,expires_at)
        VALUES (:scope,:subject,:bucket,1,:expires)
        ON CONFLICT(scope,subject_hash,bucket_start) DO UPDATE
        SET count=rate_limit_counters.count+1 RETURNING count
    """, {"scope": "preview" if preview else "chat_daily", "subject": keyed_hash(str(owner), "rate"),
          "bucket": bucket, "expires": bucket + timedelta(seconds=period * 2)})
    if count["count"] > (20 if preview else settings.max_user_daily_runs):
        raise AppError(429, "RUN_QUOTA", "当前对话额度已用完，请稍后再试。")


async def create_run(conn, owner, persona, conversation, client_id, text, fingerprint,
                     *, retry_of=None, reuse_user=None):
    active = await fetch_one(conn, """SELECT id FROM chat_runs WHERE conversation_id=:id
        AND status IN ('queued','preparing','generating','reviewing')""", {"id": conversation["id"]})
    if active:
        raise AppError(409, "RUN_ACTIVE", "当前回复还在生成，请等待或停止。")
    await run_quota(conn, owner, conversation["mode"] == "preview")
    user_id = reuse_user or uuid4()
    assistant_id, run_id = uuid4(), uuid4()
    seq = conversation["next_message_seq"]
    base = {"owner": owner, "persona": persona["id"], "conversation": conversation["id"]}
    if reuse_user is None:
        await execute(conn, """INSERT INTO messages(id,owner_id,persona_id,conversation_id,seq,role,content,status)
            VALUES (:id,:owner,:persona,:conversation,:seq,'user',:text,'completed')""",
                      {**base, "id": user_id, "seq": seq, "text": text})
        seq += 1
    await execute(conn, """INSERT INTO messages(id,owner_id,persona_id,conversation_id,seq,role,status)
        VALUES (:id,:owner,:persona,:conversation,:seq,'assistant','pending')""", {**base, "id": assistant_id, "seq": seq})
    await execute(conn, """UPDATE conversations SET next_message_seq=:next,updated_at=now()
        WHERE id=:conversation AND owner_id=:owner""", {**base, "next": seq + 1})
    examples = await fetch_all(conn, """SELECT sample_text FROM persona_examples WHERE owner_id=:owner
        AND persona_id=:persona AND approved ORDER BY created_at,id LIMIT 5""", base)
    snapshot = {"style": persona["style_json"], "examples": [row["sample_text"] for row in examples],
                "mode": conversation["mode"], "llm_model": settings.llm_model, "prompt_version": "companion-v1",
                "style_version": persona["style_version"], "context_version": persona["context_version"]}
    run = await fetch_one(conn, """INSERT INTO chat_runs(id,owner_id,persona_id,conversation_id,
        client_message_id,request_hash,user_message_id,assistant_message_id,retry_of_run_id,
        context_version,config_snapshot)
        VALUES (:id,:owner,:persona,:conversation,:client,:hash,:user,:assistant,:retry,:version,CAST(:config AS jsonb))
        RETURNING *""", {**base, "id": run_id, "client": client_id, "hash": fingerprint,
                           "user": user_id, "assistant": assistant_id, "retry": retry_of,
                           "version": persona["context_version"], "config": json_dump(snapshot)})
    await execute(conn, """INSERT INTO jobs(owner_id,kind,target_id,target_version,dedup_key,max_attempts)
        VALUES (:owner,'generate_reply',:id,:version,:dedup,1)""",
                  {"owner": owner, "id": run_id, "version": persona["context_version"], "dedup": f"generate:{run_id}"})
    await append_event(conn, run_id, "status", {"phase": "queued", "status": "queued"})
    return run


async def lock_conversation(conn, owner, conversation_id, *, active=True):
    raw = await fetch_one(conn, "SELECT persona_id FROM conversations WHERE id=:id AND owner_id=:owner",
                          {"id": conversation_id, "owner": owner})
    if not raw:
        raise not_found()
    persona = await owned_persona(conn, owner, raw["persona_id"], lock=True, active=active)
    conversation = await fetch_one(conn, "SELECT * FROM conversations WHERE id=:id AND owner_id=:owner FOR UPDATE",
                                   {"id": conversation_id, "owner": owner})
    if not conversation:
        raise not_found()
    return persona, conversation


async def lock_run(conn, owner, run_id):
    raw = await fetch_one(conn, "SELECT conversation_id FROM chat_runs WHERE id=:id AND owner_id=:owner",
                          {"id": run_id, "owner": owner})
    if not raw:
        raise not_found()
    persona, conversation = await lock_conversation(conn, owner, raw["conversation_id"], active=False)
    jobs = await fetch_all(conn, """SELECT * FROM jobs WHERE owner_id=:owner AND target_id=:id
        AND kind='generate_reply' ORDER BY id FOR UPDATE""", {"owner": owner, "id": run_id})
    run = await fetch_one(conn, "SELECT * FROM chat_runs WHERE id=:id AND owner_id=:owner FOR UPDATE",
                          {"id": run_id, "owner": owner})
    if not run:
        raise not_found()
    return persona, conversation, jobs, run
