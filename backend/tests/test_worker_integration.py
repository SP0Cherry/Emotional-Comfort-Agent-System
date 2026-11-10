"""Worker concurrency/fencing checks require the real PostgreSQL fixture."""
import asyncio
import json
from uuid import UUID, uuid4

import pytest

from app.providers.base import Completion, ProviderError
from app.providers.mock import MockProvider
from test_integration import conversation, create_persona, send


async def test_late_embedding_cannot_overwrite_edited_revision(client, account):
    from app.db import fetch_one, transaction
    from app.jobs.queue import claim_job
    from app.worker import process_job, process_once

    headers, _ = account
    persona = await create_persona(client, headers)
    chat = await conversation(client, headers, persona)
    posted = (await send(client, headers, chat, "我喜欢京剧")).json()
    assert await process_once()  # generate
    assert await process_once()  # extract
    candidates = (await client.get("/v1/memories", headers=headers, params={"persona_id": persona["id"]})).json()["items"]
    assert len(candidates) == 1
    memory = candidates[0]
    assert memory["source_message_ids"] == [posted["user_message_id"]]
    assert memory["status"] == "candidate"
    confirmation = await client.post(f"/v1/memories/{memory['id']}/confirm", headers=headers, json={"revision": 1})
    assert confirmation.status_code == 202
    old_job = await claim_job(("embed_memory",))
    assert old_job is not None

    class EditingProvider(MockProvider):
        async def embed(self, text):
            edited = await client.patch(f"/v1/memories/{memory['id']}", headers=headers, json={"revision": 1, "content": "我喜欢喝龙井茶"})
            assert edited.status_code == 200, edited.text
            return await super().embed(text)

    await process_job(old_job, EditingProvider())
    async with transaction() as conn:
        row = await fetch_one(conn, "SELECT * FROM memories WHERE id=:id", {"id": UUID(memory["id"])})
    assert row["revision"] == 2 and row["status"] == "candidate"
    assert row["embedding"] is None and row["embedding_revision"] is None
    assert row["content"] == "我喜欢喝龙井茶"
    confirmation = await client.post(f"/v1/memories/{memory['id']}/confirm", headers=headers, json={"revision": 2})
    assert confirmation.status_code == 202
    assert await process_once()
    active = (await client.get("/v1/memories", headers=headers, params={"persona_id": persona["id"], "status": "active"})).json()["items"]
    assert len(active) == 1 and active[0]["revision"] == 2


async def test_expired_generation_lease_is_terminal_and_old_worker_is_fenced(client, account):
    from app.db import execute, fetch_all, fetch_one, transaction
    from app.jobs.queue import claim_job, fail_job, watchdog_once
    from app.worker import process_job

    headers, _ = account
    persona = await create_persona(client, headers)
    chat = await conversation(client, headers, persona)
    run = (await send(client, headers, chat)).json()
    job = await claim_job()
    assert job
    async with transaction() as conn:
        await execute(conn, "UPDATE jobs SET lease_until=now()-interval '1 second' WHERE id=:id", {"id": job["id"]})
    # A provider error from the expired worker must leave atomic finalization
    # to the watchdog, rather than failing only the job and stranding the run.
    await fail_job(job, "PROVIDER_TIMEOUT")
    async with transaction() as conn:
        pending = await fetch_one(conn, "SELECT state FROM jobs WHERE id=:id", {"id": job["id"]})
    assert pending["state"] == "leased"
    await watchdog_once()

    class CountingProvider(MockProvider):
        calls = 0

        async def complete(self, *args, **kwargs):
            self.calls += 1
            return await super().complete(*args, **kwargs)

    provider = CountingProvider()
    await process_job(job, provider)
    assert provider.calls == 0
    result = (await client.get(f"/v1/runs/{run['run_id']}", headers=headers)).json()
    assert result["status"] == "interrupted"
    async with transaction() as conn:
        events = await fetch_all(conn, "SELECT * FROM run_events WHERE run_id=:id AND event_type<>'status'", {"id": UUID(run["run_id"])})
    assert len(events) == 1 and events[0]["event_type"] == "run.interrupted"


async def test_urgent_preview_has_no_memory_or_real_world_effects(client, account):
    from app.db import execute, fetch_all, fetch_one, transaction
    from app.worker import process_once

    headers, tokens = account
    persona = await create_persona(client, headers)
    async with transaction() as conn:
        await execute(conn, """INSERT INTO memories(owner_id,persona_id,content,category,status,embedding,
            embedding_model,embedding_revision,confirmed_at) VALUES(:owner,:persona,'私密家庭资料','family_memory',
            'active',CAST(:vector AS vector),'mock-hash-v1-1024',1,now())""", {"owner": UUID(tokens["user"]["id"]), "persona": UUID(persona["id"]), "vector": json.dumps([0.1] * 1024)})

    class TrackingProvider(MockProvider):
        embedding_calls = 0
        generation_calls = 0

        async def embed(self, text):
            self.embedding_calls += 1
            return await super().embed(text)

        async def complete(self, *args, **kwargs):
            if kwargs.get("purpose") == "generate":
                self.generation_calls += 1
            return await super().complete(*args, **kwargs)

    provider = TrackingProvider()
    response = await client.post(f"/v1/personas/{persona['id']}/preview", headers=headers, json={"client_message_id": str(uuid4()), "sample_question": "我想自杀，马上行动"})
    assert response.status_code == 202, response.text
    assert await process_once(provider)
    result = (await client.get(f"/v1/runs/{response.json()['run_id']}", headers=headers)).json()
    assert result["status"] == "completed"
    assert provider.embedding_calls == 0 and provider.generation_calls == 0
    async with transaction() as conn:
        safety = await fetch_one(conn, "SELECT count(*) AS count FROM safety_events")
        maintenance = await fetch_all(conn, "SELECT * FROM jobs WHERE kind<>'generate_reply'")
    assert safety["count"] == 0 and maintenance == []
    # The same input in a real conversation records a safety event, without
    # pretending that an external contact has been reached.
    chat = await conversation(client, headers, persona)
    await send(client, headers, chat, "我想自杀，马上行动")
    assert await process_once(provider)
    async with transaction() as conn:
        safety = await fetch_one(conn, "SELECT count(*) AS count FROM safety_events WHERE severity='urgent'")
        contacts = await fetch_one(conn, "SELECT count(*) AS count FROM alert_deliveries")
    assert safety["count"] == 1 and contacts["count"] == 0


async def test_running_cancellation_closes_provider_and_never_publishes_partial_text(client, account):
    from app.db import fetch_one, transaction
    from app.jobs.queue import claim_job
    from app.worker import process_job

    headers, _ = account
    persona = await create_persona(client, headers)
    chat = await conversation(client, headers, persona)
    run = (await send(client, headers, chat)).json()
    job = await claim_job()
    started, closed = asyncio.Event(), asyncio.Event()

    class SlowProvider(MockProvider):
        async def complete(self, *args, **kwargs):
            if kwargs.get("purpose") == "generate":
                started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    # A transport may report its own close failure after task
                    # cancellation; this must not bypass terminal finalization.
                    raise ProviderError("PROVIDER_STREAM_INTERRUPTED") from None
                finally:
                    closed.set()
            return await super().complete(*args, **kwargs)

    task = asyncio.create_task(process_job(job, SlowProvider()))
    await asyncio.wait_for(started.wait(), 3)
    response = await client.post(f"/v1/runs/{run['run_id']}/cancel", headers=headers)
    assert response.status_code in (200, 202)
    await asyncio.wait_for(task, 3)
    assert closed.is_set()
    snapshot = (await client.get(f"/v1/runs/{run['run_id']}", headers=headers)).json()
    assert snapshot["status"] == "cancelled"
    async with transaction() as conn:
        message = await fetch_one(conn, "SELECT content,status FROM messages WHERE id=:id", {"id": UUID(run["assistant_message_id"])})
    assert message == {"content": "", "status": "cancelled"}


async def test_rejected_model_output_never_reaches_messages_or_events(client, account):
    from app.db import fetch_all, transaction
    from app.worker import process_once

    headers, _ = account
    persona = await create_persona(client, headers)
    chat = await conversation(client, headers, persona)
    run = (await send(client, headers, chat)).json()

    class UnsafeProvider(MockProvider):
        async def complete(self, *args, **kwargs):
            if kwargs.get("purpose") == "generate":
                return Completion("我就是您的女儿，只有我懂您。", "unsafe-test")
            return await super().complete(*args, **kwargs)

    assert await process_once(UnsafeProvider())
    async with transaction() as conn:
        messages = await fetch_all(conn, "SELECT content FROM messages WHERE conversation_id=:id AND role='assistant'", {"id": UUID(chat["id"])})
        events = await fetch_all(conn, "SELECT payload FROM run_events WHERE run_id=:id", {"id": UUID(run["run_id"])})
    encoded = json.dumps({"messages": messages, "events": events}, ensure_ascii=False)
    assert "我就是您的女儿" not in encoded and "只有我懂您" not in encoded
    assert messages[0]["content"]


async def test_finalization_uses_wall_clock_and_rolls_back_expired_result(client, account):
    from app.db import execute, fetch_one, transaction
    from app.jobs.queue import LeaseFenceLost, claim_job, complete_job, lock_run, terminal

    headers, _ = account
    persona = await create_persona(client, headers)
    chat = await conversation(client, headers, persona)
    run = (await send(client, headers, chat)).json()
    job = await claim_job()
    assert job
    with pytest.raises(LeaseFenceLost):
        async with transaction() as conn:
            locked = await lock_run(conn, job)
            assert locked
            await execute(conn, "UPDATE jobs SET lease_until=clock_timestamp()+interval '50 milliseconds' WHERE id=:id", {"id": job["id"]})
            await asyncio.sleep(0.1)
            clocks = await fetch_one(conn, "SELECT now()<lease_until AS transaction_clock_valid,clock_timestamp()>lease_until AS wall_clock_expired FROM jobs WHERE id=:id", {"id": job["id"]})
            assert clocks == {"transaction_clock_valid": True, "wall_clock_expired": True}
            await terminal(conn, job, locked[3], "completed", content="This expired result must roll back")
    async with transaction() as conn:
        row = await fetch_one(conn, "SELECT status FROM chat_runs WHERE id=:id", {"id": UUID(run["run_id"])})
        message = await fetch_one(conn, "SELECT content,status FROM messages WHERE id=:id", {"id": UUID(run["assistant_message_id"])})
    assert row["status"] == "queued"
    assert message == {"content": "", "status": "pending"}
    # The same completion fence also rolls back maintenance writes made earlier
    # in the transaction if its lease expires before the final commit decision.
    with pytest.raises(LeaseFenceLost):
        async with transaction() as conn:
            await execute(conn, "UPDATE jobs SET lease_until=clock_timestamp()+interval '50 milliseconds' WHERE id=:id", {"id": job["id"]})
            await execute(conn, "UPDATE messages SET content='uncommitted maintenance result' WHERE id=:id", {"id": UUID(run["assistant_message_id"])})
            await asyncio.sleep(0.1)
            await complete_job(conn, job)
    async with transaction() as conn:
        message = await fetch_one(conn, "SELECT content FROM messages WHERE id=:id", {"id": UUID(run["assistant_message_id"])})
    assert message["content"] == ""
