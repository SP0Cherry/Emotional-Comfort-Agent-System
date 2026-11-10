import asyncio
import json

from app.agent.prompts import PROMPT_VERSION, build_messages
from app.agent.review import REVIEW_REPLY, SUPPORT_REPLY, review_output
from app.agent.router import classify
from app.config import settings
from app.db import execute, fetch_all, fetch_one, transaction
from app.jobs.queue import abort_reason, add_event, complete_job, enqueue, lock_run, terminal


class PipelineAborted(Exception):
    pass


def record_usage(result):
    return {"model": result.model, "usage": result.usage, "usage_status": "known" if result.usage is not None else "unknown"}


async def phase(job, value):
    async with transaction() as conn:
        locked = await lock_run(conn, job)
        if not locked:
            raise PipelineAborted()
        persona, conversation, _, run = locked
        reason = abort_reason(persona, run, job)
        if reason:
            if reason != "terminal":
                await terminal(conn, job, run, "cancelled" if reason == "cancelled" else "interrupted", error="CANCELLED" if reason == "cancelled" else "STALE_CONTEXT")
            else:
                await complete_job(conn, job)
            return None
        await execute(conn, "UPDATE chat_runs SET status=:status,started_at=COALESCE(started_at,now()),updated_at=now() WHERE id=:id", {"id": run["id"], "status": value})
        await add_event(conn, run, "status", {"phase": value, "status": value})
        return persona, conversation, run


async def generate_reply(job, provider):
    state = await phase(job, "preparing")
    if not state:
        return
    persona, conversation, run = state
    async with transaction() as conn:
        current = await fetch_one(conn, "SELECT * FROM messages WHERE id=:id AND owner_id=:owner AND role='user' AND status='completed'", {"id": run["user_message_id"], "owner": run["owner_id"]})
        if not current:
            raise PipelineAborted()
        examples = await fetch_all(conn, "SELECT sample_text FROM persona_examples WHERE persona_id=:id AND owner_id=:owner AND approved=true ORDER BY created_at LIMIT 5", {"id": persona["id"], "owner": run["owner_id"]})
        summary_matches = conversation["summary_context_version"] == persona["context_version"]
        history = await fetch_all(conn, """SELECT * FROM (
            SELECT * FROM messages WHERE conversation_id=:conversation AND owner_id=:owner
            AND status='completed' AND seq>:until AND seq<:current
            ORDER BY seq DESC LIMIT 24) recent ORDER BY seq""", {"conversation": conversation["id"], "owner": run["owner_id"], "until": conversation["summary_until_seq"] if summary_matches else 0, "current": current["seq"]})
        memory_fingerprint = await fetch_one(conn, """SELECT md5(coalesce(string_agg(
            id::text||':'||revision::text||':'||status,',' ORDER BY id),'')) AS value
            FROM memories WHERE persona_id=:id AND owner_id=:owner AND confirmed_at IS NOT NULL
            AND status IN ('indexing','active')""", {"id": persona["id"], "owner": run["owner_id"]}) if conversation["mode"] == "chat" else None
    route, routes, router_failed = await classify(provider, current["content"])
    usage = {"route": [record_usage(r) for r in routes], "router_failed": router_failed}
    memories = []
    if route.risk == "none" and conversation["mode"] == "chat":
        # Avoid even an embedding request when there are no usable memories.
        async with transaction() as conn:
            available = await fetch_one(conn, """SELECT id FROM memories WHERE owner_id=:owner AND persona_id=:persona
                AND status='active' AND embedding_model=:model AND embedding_revision=revision
                AND (valid_until IS NULL OR valid_until>now()) LIMIT 1""", {"owner": run["owner_id"], "persona": persona["id"], "model": provider.embedding_model})
        if available:
            vector = await provider.embed(current["content"])
            async with transaction() as conn:
                memories = await fetch_all(conn, """SELECT id,content,category,revision,embedding <=> CAST(:vector AS vector) AS distance
                    FROM memories WHERE owner_id=:owner AND persona_id=:persona AND status='active'
                    AND embedding IS NOT NULL AND embedding_model=:model AND embedding_revision=revision
                    AND confirmed_at IS NOT NULL AND (valid_until IS NULL OR valid_until>now())
                    ORDER BY embedding <=> CAST(:vector AS vector) LIMIT 5""", {"owner": run["owner_id"], "persona": persona["id"], "model": provider.embedding_model, "vector": json.dumps(vector)})
            # A conservative lexical relevance gate avoids an uncalibrated
            # universal cosine cutoff. Semantic thresholds await the Chinese eval.
            def relevant(memory):
                query = current["content"]
                if memory["category"] == "preference" and any(word in query for word in ("喜欢什么", "爱好", "记得")):
                    return True
                return any(query[i:i+2] in memory["content"] for i in range(len(query)-1))
            memories = [m for m in memories if relevant(m)]
    if not await phase(job, "generating"):
        return
    if route.risk == "urgent":
        answer = SUPPORT_REPLY
    elif route.risk == "review" or router_failed:
        answer = REVIEW_REPLY
    else:
        snapshot = run["config_snapshot"] or {}
        messages = build_messages(
            style=snapshot.get("style", snapshot.get("style_json", persona["style_json"])),
            examples=snapshot.get("examples", [e["sample_text"] for e in examples]),
            memories=memories, summary=conversation["summary"] if summary_matches else "",
            history=history, current=current, strategy=route.response_strategy,
        )
        async with asyncio.timeout(settings.generation_timeout_seconds):
            result = await provider.complete(messages, purpose="generate", max_tokens=256)
        answer = result.text
        usage["generation"] = record_usage(result)
    if not await phase(job, "reviewing"):
        return
    if route.risk == "none" and not router_failed:
        answer, violation, review = await review_output(provider, answer, current["content"], memories)
        usage["review_failure"] = violation
        if review:
            usage["review"] = record_usage(review)
    usage["prompt_version"] = PROMPT_VERSION
    async with transaction() as conn:
        locked = await lock_run(conn, job)
        if not locked:
            raise PipelineAborted()
        latest_persona, latest_conversation, _, latest_run = locked
        reason = abort_reason(latest_persona, latest_run, job)
        if reason:
            if reason != "terminal":
                await terminal(conn, job, latest_run, "cancelled" if reason == "cancelled" else "interrupted", error="CANCELLED" if reason == "cancelled" else "STALE_CONTEXT")
            else:
                await complete_job(conn, job)
            return
        if conversation["mode"] == "chat" and route.risk == "none":
            latest_fingerprint = await fetch_one(conn, """SELECT md5(coalesce(string_agg(
                id::text||':'||revision::text||':'||status,',' ORDER BY id),'')) AS value
                FROM memories WHERE persona_id=:id AND owner_id=:owner AND confirmed_at IS NOT NULL
                AND status IN ('indexing','active')""", {"id": persona["id"], "owner": run["owner_id"]})
            summary_changed = any(latest_conversation[key] != conversation[key] for key in ("summary", "summary_until_seq", "summary_context_version"))
            if latest_fingerprint != memory_fingerprint or summary_changed:
                await terminal(conn, job, latest_run, "interrupted", error="STALE_MEMORY")
                return
        for memory in memories:
            still_confirmed = await fetch_one(conn, """SELECT id FROM memories WHERE id=:id AND owner_id=:owner
                AND persona_id=:persona AND status='active' AND revision=:revision AND embedding_revision=revision
                AND embedding_model=:model AND confirmed_at IS NOT NULL AND (valid_until IS NULL OR valid_until>now())""", {"id": memory["id"], "owner": run["owner_id"], "persona": persona["id"], "revision": memory["revision"], "model": provider.embedding_model})
            if not still_confirmed:
                await terminal(conn, job, latest_run, "interrupted", error="STALE_MEMORY")
                return
        if (route.risk == "urgent" or (route.risk == "review" and not router_failed)) and conversation["mode"] == "chat":
            await execute(conn, """INSERT INTO safety_events(owner_id,run_id,risk_type,severity,policy_version)
                VALUES(:owner,:run,'input_risk',:severity,'support-v1-no-external-contact')""", {"owner": run["owner_id"], "run": run["id"], "severity": route.risk})
            # This MVP has no staffed support delivery. Never claim contact was sent.
        await terminal(conn, job, latest_run, "completed", content=answer, usage=usage)
        if conversation["mode"] == "chat" and route.risk == "none" and not router_failed:
            await enqueue(conn, owner_id=run["owner_id"], kind="extract_memory", target_id=run["id"], version=run["context_version"], dedup_key=f"extract:{run['user_message_id']}:{run['context_version']}")
            if current["seq"] > 24:
                await enqueue(conn, owner_id=run["owner_id"], kind="summarize", target_id=run["id"], version=run["context_version"], dedup_key=f"summary:{conversation['id']}:{current['seq']}:{run['context_version']}")
