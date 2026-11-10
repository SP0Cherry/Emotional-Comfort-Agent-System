import asyncio
from io import BytesIO
from uuid import UUID, uuid4

from PIL import Image

from conftest import login


async def create_persona(client, headers, **fields):
    response = await client.post("/v1/personas", headers=headers, json={
        "display_name": "小雨 AI 陪伴", "style": {"address_user": "妈妈"}, **fields,
    })
    assert response.status_code == 201, response.text
    return response.json()


async def conversation(client, headers, persona):
    response = await client.post("/v1/conversations", headers=headers, json={"persona_id": persona["id"]})
    assert response.status_code == 201, response.text
    return response.json()


async def send(client, headers, chat, text="我喜欢喝龙井茶。", message_id=None):
    return await client.post(f"/v1/conversations/{chat['id']}/runs", headers=headers, json={
        "client_message_id": str(message_id or uuid4()), "text": text,
    })


async def test_refresh_rotation_otp_replay_and_private_ownership(client, account):
    headers, tokens = account
    other_headers, _ = await login(client, "13800000002")
    persona = await create_persona(client, headers)
    response = await client.get(f"/v1/personas/{persona['id']}", headers=other_headers)
    assert response.status_code == 404
    response = await client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200
    assert response.json()["refresh_token"] != tokens["refresh_token"]
    response = await client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 401


async def test_concurrent_idempotency_and_one_active_run(client, account):
    headers, _ = account
    persona = await create_persona(client, headers)
    chat = await conversation(client, headers, persona)
    message_id = uuid4()
    responses = await asyncio.gather(*(send(client, headers, chat, message_id=message_id) for _ in range(10)))
    assert all(r.status_code in {200, 202} for r in responses), [r.text for r in responses]
    assert len({r.json()["run_id"] for r in responses}) == 1
    active = await send(client, headers, chat, "另一条消息")
    assert active.status_code == 409
    assert active.json()["error"]["code"] == "RUN_ACTIVE"
    conflict = await send(client, headers, chat, "不同正文", message_id=message_id)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    from app.db import fetch_one, transaction
    async with transaction() as conn:
        row = await fetch_one(conn, "SELECT count(*) AS count FROM messages WHERE conversation_id=:id", {"id": UUID(chat["id"])})
        assert row["count"] == 2


async def test_worker_publishes_checked_reply_and_replays_events(client, account):
    headers, _ = account
    persona = await create_persona(client, headers)
    chat = await conversation(client, headers, persona)
    response = await send(client, headers, chat)
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    from app.worker import process_once
    await process_once()
    snapshot = await client.get(f"/v1/runs/{run_id}", headers=headers)
    assert snapshot.status_code == 200, snapshot.text
    assert snapshot.json()["status"] == "completed", snapshot.text
    events = await client.get(f"/v1/runs/{run_id}/events", headers=headers)
    assert events.status_code == 200
    assert "event: message.completed" in events.text
    assert "reasoning_content" not in events.text
    cursor = snapshot.json()["last_event_seq"]
    replay = await client.get(f"/v1/runs/{run_id}/events?after_seq={cursor}", headers=headers)
    assert "message.completed" not in replay.text
    invalid = await client.get(f"/v1/runs/{run_id}/events?after_seq={cursor + 10}", headers=headers)
    assert invalid.status_code == 400
    stranger, _ = await login(client, "13800000002")
    assert (await client.get(f"/v1/runs/{run_id}/events", headers=stranger)).status_code == 404


async def test_cancelled_retry_reuses_user_message_and_checks_latest_run(client, account):
    headers, _ = account
    persona = await create_persona(client, headers)
    chat = await conversation(client, headers, persona)
    original = (await send(client, headers, chat)).json()
    cancelled = await client.post(f"/v1/runs/{original['run_id']}/cancel", headers=headers)
    assert cancelled.status_code in {200, 202}, cancelled.text
    retry = await client.post(f"/v1/runs/{original['run_id']}/retry", headers=headers,
                              json={"client_message_id": str(uuid4())})
    assert retry.status_code == 202, retry.text
    assert retry.json()["user_message_id"] == original["user_message_id"]
    from app.db import fetch_one, transaction
    async with transaction() as conn:
        row = await fetch_one(conn, "SELECT count(*) AS count FROM messages WHERE conversation_id=:id AND role='user'",
                              {"id": UUID(chat["id"])})
        assert row["count"] == 1


async def test_avatar_is_decoded_reencoded_and_requires_owner(client, account):
    headers, _ = account
    buffer = BytesIO()
    Image.new("RGB", (1400, 700), color="green").save(buffer, "PNG")
    response = await client.post("/v1/assets/avatar", headers=headers,
                                 files={"file": ("unsafe-name.png", buffer.getvalue(), "image/png")})
    assert response.status_code == 201, response.text
    asset = response.json()
    asset_id = asset.get("asset_id", asset.get("id"))
    link = await client.get(f"/v1/assets/{asset_id}/read-url", headers=headers)
    assert link.status_code == 200, link.text
    url = link.json().get("url", link.json().get("read_url"))
    image_response = await client.get(url)
    assert image_response.status_code == 200, image_response.text
    cleaned = Image.open(BytesIO(image_response.content))
    assert cleaned.format == "JPEG" and max(cleaned.size) <= 1024
    assert not cleaned.getexif()
    fake = await client.post("/v1/assets/avatar", headers=headers,
                             files={"file": ("fake.jpg", b"not an image", "image/jpeg")})
    assert fake.status_code in {400, 413, 415, 422}


async def test_reset_hides_old_context_and_purge_removes_it(client, account):
    headers, _ = account
    persona = await create_persona(client, headers)
    chat = await conversation(client, headers, persona)
    await send(client, headers, chat)
    reset = await client.post(f"/v1/personas/{persona['id']}/reset-context", headers=headers, json={"confirm": True})
    assert reset.status_code == 202, reset.text
    blocked = await client.get(f"/v1/conversations/{chat['id']}/messages", headers=headers)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "CONTEXT_RESETTING"
    from app.worker import process_once
    # The queued generation must become stale, then purge may run.
    for _ in range(4):
        await process_once()
    history = await client.get("/v1/conversations", headers=headers, params={"persona_id": persona["id"]})
    assert history.status_code == 200, history.text
    assert history.json()["items"] == []
