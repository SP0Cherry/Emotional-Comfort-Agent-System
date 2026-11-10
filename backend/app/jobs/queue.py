import json
from datetime import datetime, timezone

from app.config import settings
from app.db import execute, fetch_all, fetch_one, transaction


ACTIVE_STATES = ("queued", "preparing", "generating", "reviewing")
GENERATION = ("generate_reply",)
MAINTENANCE = ("extract_memory", "embed_memory", "summarize", "purge_data", "send_alert")


class LeaseFenceLost(Exception):
    """Roll back a business transaction whose lease expired while it waited."""


async def claim_job(kinds=GENERATION):
    # Claim commits before any persona lock is requested.
    async with transaction() as conn:
        return await fetch_one(conn, """
            WITH picked AS (
                SELECT id FROM jobs
                WHERE state='queued' AND kind=ANY(:kinds)
                  AND available_at<=now() AND attempts<max_attempts
                ORDER BY available_at,created_at,id
                FOR UPDATE SKIP LOCKED LIMIT 1
            ) UPDATE jobs j SET state='leased',attempts=attempts+1,
                lease_until=clock_timestamp()+(:lease_seconds * interval '1 second'),
                lease_token=gen_random_uuid(),updated_at=now()
            FROM picked p WHERE j.id=p.id RETURNING j.*
        """, {"kinds": list(kinds), "lease_seconds": settings.lease_seconds})


async def renew_lease(job):
    async with transaction() as conn:
        row = await fetch_one(conn, """UPDATE jobs SET
            lease_until=clock_timestamp()+(:seconds * interval '1 second'),updated_at=now()
            WHERE id=:id AND lease_token=:token AND state='leased' AND lease_until>clock_timestamp()
            RETURNING id""", {"id": job["id"], "token": job["lease_token"], "seconds": settings.lease_seconds})
        return row is not None


def lease_matches(current, job):
    return bool(current and current["state"] == "leased" and
                current["lease_token"] == job["lease_token"] and
                current.get("lease_valid", current["lease_until"] > datetime.now(timezone.utc)))


async def lock_run(conn, job):
    """One lock order everywhere: persona -> conversation -> job -> run.

    The initial unlocked read finds identifiers only. All authority is rechecked
    after locking; resets may delete the rows between the reads.
    """
    target = await fetch_one(conn, "SELECT * FROM chat_runs WHERE id=:id AND owner_id=:owner", {"id": job["target_id"], "owner": job["owner_id"]})
    if not target:
        return None
    persona = await fetch_one(conn, "SELECT * FROM personas WHERE id=:id AND owner_id=:owner FOR UPDATE", {"id": target["persona_id"], "owner": job["owner_id"]})
    conversation = await fetch_one(conn, "SELECT * FROM conversations WHERE id=:id AND owner_id=:owner FOR UPDATE", {"id": target["conversation_id"], "owner": job["owner_id"]})
    current_job = await fetch_one(conn, "SELECT *,lease_until>clock_timestamp() AS lease_valid FROM jobs WHERE id=:id FOR UPDATE", {"id": job["id"]})
    run = await fetch_one(conn, "SELECT * FROM chat_runs WHERE id=:id AND owner_id=:owner FOR UPDATE", {"id": job["target_id"], "owner": job["owner_id"]})
    if not persona or not conversation or not run or not lease_matches(current_job, job):
        return None
    return persona, conversation, current_job, run


def abort_reason(persona, run, job):
    if run["status"] not in ACTIVE_STATES:
        return "terminal"
    if run["cancel_requested_at"]:
        return "cancelled"
    if persona["status"] != "active" or persona["context_version"] != run["context_version"] or run["context_version"] != job["target_version"]:
        return "stale_context"
    return None


async def add_event(conn, run, event_type, payload):
    seq = await fetch_one(conn, "UPDATE chat_runs SET next_event_seq=next_event_seq+1 WHERE id=:id RETURNING next_event_seq-1 AS seq", {"id": run["id"]})
    data = {"run_id": str(run["id"]), "seq": seq["seq"], **payload}
    await execute(conn, "INSERT INTO run_events(run_id,seq,event_type,payload) VALUES(:id,:seq,:event,CAST(:payload AS jsonb))", {"id": run["id"], "seq": seq["seq"], "event": event_type, "payload": json.dumps(data, ensure_ascii=False)})


async def terminal(conn, job, run, status, *, content="", error=None, usage=None, allow_expired=False):
    if run["status"] not in ACTIVE_STATES:
        await complete_job(conn, job)
        return
    # Fence using wall-clock time immediately before publishing. now() would
    # remain frozen at transaction start even after waiting on a persona lock.
    # Taking ownership of finalization and writing all visible results occurs
    # in this same transaction, so a lost lease rolls everything back.
    finalized = await fetch_one(conn, """UPDATE jobs SET state=:state,error_code=:error,
        lease_until=NULL,lease_token=NULL,updated_at=now()
        WHERE id=:id AND state IN ('queued','leased')
          AND lease_token IS NOT DISTINCT FROM :token
          AND (:allow_expired OR (state='leased' AND lease_until>clock_timestamp()))
        RETURNING id""", {"id": job["id"], "token": job["lease_token"], "state": "completed" if status in ("completed", "cancelled") else "failed", "error": error, "allow_expired": allow_expired})
    if not finalized:
        raise LeaseFenceLost()
    await execute(conn, "UPDATE messages SET content=:content,status=:status,updated_at=now() WHERE id=:id AND owner_id=:owner", {"id": run["assistant_message_id"], "owner": run["owner_id"], "content": content if status == "completed" else "", "status": status})
    await execute(conn, """UPDATE chat_runs SET status=:status,error_code=:error,
        usage_json=CAST(:usage AS jsonb),finished_at=now(),updated_at=now() WHERE id=:id""", {"id": run["id"], "status": status, "error": error, "usage": json.dumps(usage or {})})
    payload = {"status": status, "error_code": error}
    if status == "completed":
        payload.update({"message_id": str(run["assistant_message_id"]), "content": content})
    await add_event(conn, run, "message.completed" if status == "completed" else f"run.{status}", payload)


async def complete_job(conn, job, error=None):
    completed = await fetch_one(conn, """UPDATE jobs SET state='completed',error_code=:error,
        lease_until=NULL,lease_token=NULL,updated_at=now()
        WHERE id=:id AND state='leased' AND lease_token=:token AND lease_until>clock_timestamp()
        RETURNING id""", {"id": job["id"], "token": job["lease_token"], "error": error})
    if not completed:
        current = await fetch_one(conn, "SELECT state,lease_token FROM jobs WHERE id=:id", {"id": job["id"]})
        if current and current["state"] == "leased" and current["lease_token"] == job["lease_token"]:
            # A maintenance handler may already have written its result. Raising
            # rolls back both that result and the failed completion attempt.
            raise LeaseFenceLost()


async def enqueue(conn, *, owner_id, kind, target_id, version, dedup_key, max_attempts=3):
    await execute(conn, """INSERT INTO jobs(owner_id,kind,target_id,target_version,dedup_key,max_attempts)
        VALUES(:owner,:kind,:target,:version,:dedup,:attempts) ON CONFLICT(dedup_key) DO NOTHING""", {"owner": owner_id, "kind": kind, "target": target_id, "version": version, "dedup": dedup_key, "attempts": max_attempts})


async def fail_job(job, error):
    if job["kind"] == "generate_reply":
        async with transaction() as conn:
            locked = await lock_run(conn, job)
            if locked:
                persona, _, _, run = locked
                reason = abort_reason(persona, run, job)
                status = "cancelled" if reason == "cancelled" else "interrupted" if reason == "stale_context" else "failed"
                await terminal(conn, job, run, status, error=error)
            else:
                # Only an absent target can be finalized without a run lock.
                # If the lease merely expired, leave it for the watchdog to
                # atomically interrupt both run and job (never strand the run).
                target = await fetch_one(conn, "SELECT id FROM chat_runs WHERE id=:id AND owner_id=:owner", {"id": job["target_id"], "owner": job["owner_id"]})
                if not target:
                    await execute(conn, "UPDATE jobs SET state='failed',error_code=:error,lease_until=NULL,lease_token=NULL,updated_at=now() WHERE id=:id AND state='leased' AND lease_token=:token", {"id": job["id"], "token": job["lease_token"], "error": error})
        return
    async with transaction() as conn:
        retry = job["attempts"] < job["max_attempts"]
        delay = (2, 10, 30)[min(job["attempts"] - 1, 2)]
        await execute(conn, """UPDATE jobs SET state=:state,error_code=:error,
            lease_until=NULL,lease_token=NULL,available_at=now()+(:delay*interval '1 second'),updated_at=now()
            WHERE id=:id AND state='leased' AND lease_token=:token AND lease_until>clock_timestamp()""", {"id": job["id"], "token": job["lease_token"], "state": "queued" if retry else "failed", "error": error, "delay": delay})


async def watchdog_once():
    # Scan identifiers without locks, then acquire business locks in normal order.
    async with transaction() as conn:
        stale = await fetch_all(conn, """SELECT * FROM jobs WHERE
            (state='leased' AND lease_until<=clock_timestamp()) OR
            (state='queued' AND kind='generate_reply' AND created_at<now()-interval '30 seconds')
            ORDER BY created_at LIMIT 100""")
    for job in stale:
        if job["kind"] == "generate_reply":
            async with transaction() as conn:
                target = await fetch_one(conn, "SELECT * FROM chat_runs WHERE id=:id AND owner_id=:owner", {"id": job["target_id"], "owner": job["owner_id"]})
                if target:
                    await fetch_one(conn, "SELECT id FROM personas WHERE id=:id FOR UPDATE", {"id": target["persona_id"]})
                    await fetch_one(conn, "SELECT id FROM conversations WHERE id=:id FOR UPDATE", {"id": target["conversation_id"]})
                current = await fetch_one(conn, "SELECT *,lease_until<=clock_timestamp() AS expired,created_at<now()-interval '30 seconds' AS old FROM jobs WHERE id=:id FOR UPDATE", {"id": job["id"]})
                if not current or not ((current["state"] == "leased" and current["expired"]) or (current["state"] == "queued" and current["old"])):
                    continue
                run = await fetch_one(conn, "SELECT * FROM chat_runs WHERE id=:id FOR UPDATE", {"id": job["target_id"]}) if target else None
                error = "WORKER_INTERRUPTED" if current["state"] == "leased" else "QUEUE_TIMEOUT"
                if run and run["status"] in ACTIVE_STATES:
                    # terminal() uses the matching (possibly expired) token. Locks
                    # prevent renewal or final submission racing this decision.
                    await terminal(conn, current, run, "interrupted" if current["state"] == "leased" else "failed", error=error, allow_expired=True)
                await execute(conn, "UPDATE jobs SET state='failed',error_code=:error,lease_until=NULL,lease_token=NULL,updated_at=now() WHERE id=:id", {"id": job["id"], "error": error})
        else:
            async with transaction() as conn:
                await execute(conn, """UPDATE jobs SET state=CASE WHEN attempts<max_attempts THEN 'queued' ELSE 'failed' END,
                    available_at=now()+interval '10 seconds',lease_until=NULL,lease_token=NULL,error_code='WORKER_INTERRUPTED',updated_at=now()
                    WHERE id=:id AND state='leased' AND lease_until<=clock_timestamp()""", {"id": job["id"]})
