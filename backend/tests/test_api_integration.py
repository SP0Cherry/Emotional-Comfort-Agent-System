from io import BytesIO
from uuid import UUID, uuid4

from PIL import Image

from conftest import login
from test_integration import conversation, create_persona, send


async def drain_jobs(limit=20):
    from app.worker import process_once

    for _ in range(limit):
        if not await process_once():
            return
    raise AssertionError("Development jobs did not settle")


async def candidate_memory(client, headers, persona):
    chat = await conversation(client, headers, persona)
    sent = await send(client, headers, chat, "我喜欢喝龙井茶。")
    assert sent.status_code == 202, sent.text
    await drain_jobs()
    result = await client.get("/v1/memories", headers=headers, params={"persona_id": persona["id"]})
    assert result.status_code == 200, result.text
    assert len(result.json()["items"]) == 1
    memory = result.json()["items"][0]
    assert memory["status"] == "candidate"
    return memory, sent.json()


async def test_memory_lifecycle_recall_edit_revision_remove_and_source_blocking(client, account):
    from app.db import execute, fetch_one, transaction

    headers, _ = account
    persona = await create_persona(client, headers)
    memory, source_run = await candidate_memory(client, headers, persona)
    confirmed = await client.post(f"/v1/memories/{memory['id']}/confirm", headers=headers,
                                  json={"revision": memory["revision"]})
    assert confirmed.status_code == 202, confirmed.text
    assert confirmed.json()["status"] == "indexing"
    await drain_jobs()
    page = await client.get("/v1/memories", headers=headers, params={"persona_id": persona["id"]})
    assert page.json()["items"][0]["status"] == "active"

    # A new conversation has no source history: recall must use the confirmed memory.
    fresh_chat = await conversation(client, headers, persona)
    recall = await send(client, headers, fresh_chat, "您还记得我喜欢什么吗？")
    assert recall.status_code == 202, recall.text
    await drain_jobs()
    reply = await client.get(f"/v1/runs/{recall.json()['run_id']}", headers=headers)
    assert reply.json()["status"] == "completed", reply.text
    assert "龙井茶" in reply.json()["assistant_message"]["content"]

    edited = await client.patch(f"/v1/memories/{memory['id']}", headers=headers,
                                json={"revision": 1, "content": "我现在更喜欢喝白茶。"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["revision"] == 2 and edited.json()["status"] == "candidate"
    async with transaction() as conn:
        row = await fetch_one(conn, """SELECT embedding IS NULL AS cleared,embedding_revision,confirmed_at
            FROM memories WHERE id=:id""", {"id": UUID(memory["id"])})
        assert row["cleared"] and row["embedding_revision"] is None and row["confirmed_at"] is None
    stale = await client.post(f"/v1/memories/{memory['id']}/confirm", headers=headers, json={"revision": 1})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CONFLICT"

    removed = await client.delete(f"/v1/memories/{memory['id']}", headers=headers)
    assert removed.status_code == 204
    async with transaction() as conn:
        source = await fetch_one(conn, "SELECT memory_blocked FROM messages WHERE id=:id",
                                 {"id": UUID(source_run["user_message_id"])})
        assert source["memory_blocked"]
        assert await fetch_one(conn, "SELECT id FROM memories WHERE id=:id", {"id": UUID(memory["id"])}) is None
        # Replaying extraction with a fresh queue identity must not resurrect removed data.
        await execute(conn, """INSERT INTO jobs(owner_id,kind,target_id,target_version,
            dedup_key,max_attempts) VALUES (:owner,'extract_memory',:run,1,:key,3)""",
                      {"owner": UUID(persona["owner_id"]), "run": UUID(source_run["run_id"]),
                       "key": f"test-reextract:{uuid4()}"})
    await drain_jobs()
    page = await client.get("/v1/memories", headers=headers, params={"persona_id": persona["id"]})
    assert page.json()["items"] == []


async def test_persona_optimistic_style_conflict_preserves_winning_edit(client, account):
    headers, _ = account
    persona = await create_persona(client, headers, examples=["您慢慢说，我听着。"])
    edit = await client.patch(f"/v1/personas/{persona['id']}", headers=headers,
                              json={"style_version": 1, "style": {"address_user": "爸爸"}, "examples": ["慢慢聊。"]})
    assert edit.status_code == 200, edit.text
    assert edit.json()["style_version"] == 2 and edit.json()["style"]["address_user"] == "爸爸"
    conflict = await client.patch(f"/v1/personas/{persona['id']}", headers=headers,
                                  json={"style_version": 1, "display_name": "迟到的修改"})
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "VERSION_CONFLICT"
    current = await client.get(f"/v1/personas/{persona['id']}", headers=headers)
    assert current.json()["display_name"] == persona["display_name"]
    assert current.json()["examples"] == ["慢慢聊。"]


async def test_preview_idempotency_never_creates_extra_conversations_or_memory_jobs(client, account):
    from app.db import fetch_all, fetch_one, transaction

    headers, _ = account
    persona = await create_persona(client, headers)
    message_id = str(uuid4())
    body = {"client_message_id": message_id, "sample_question": "我喜欢听京剧。"}
    path = f"/v1/personas/{persona['id']}/preview"
    first = await client.post(path, headers=headers, json=body)
    duplicate = await client.post(path, headers=headers, json=body)
    assert first.status_code == 202 and duplicate.status_code == 200, (first.text, duplicate.text)
    assert first.json()["run_id"] == duplicate.json()["run_id"]
    conflict = await client.post(path, headers=headers, json={**body, "sample_question": "另一个问题。"})
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    await drain_jobs()
    async with transaction() as conn:
        chats = await fetch_all(conn, "SELECT mode FROM conversations WHERE persona_id=:id", {"id": UUID(persona["id"])})
        assert chats == [{"mode": "preview"}]
        jobs = await fetch_all(conn, "SELECT kind FROM jobs WHERE owner_id=:owner", {"owner": UUID(persona["owner_id"])})
        assert jobs == [{"kind": "generate_reply"}]
        row = await fetch_one(conn, "SELECT count(*) AS n FROM memories WHERE persona_id=:id", {"id": UUID(persona["id"])})
        assert row["n"] == 0


async def test_memory_and_avatar_routes_return_404_for_other_owner(client, account):
    headers, _ = account
    stranger, _ = await login(client, "13800000002")
    persona = await create_persona(client, headers)
    memory, _ = await candidate_memory(client, headers, persona)
    assert (await client.get("/v1/memories", headers=stranger,
                             params={"persona_id": persona["id"]})).status_code == 404
    for method, suffix, body in (("post", "/confirm", {"revision": 1}),
                                  ("post", "/reject", {"revision": 1}),
                                  ("patch", "", {"revision": 1, "content": "越权修改"}),
                                  ("delete", "", None)):
        response = await client.request(method, f"/v1/memories/{memory['id']}{suffix}", headers=stranger,
                                        **({"json": body} if body is not None else {}))
        assert response.status_code == 404, response.text
    raw = BytesIO()
    Image.new("RGB", (20, 20), "blue").save(raw, "PNG")
    uploaded = await client.post("/v1/assets/avatar", headers=headers,
                                 files={"file": ("avatar.png", raw.getvalue(), "image/png")})
    assert uploaded.status_code == 201, uploaded.text
    asset_id = uploaded.json()["asset_id"]
    assert (await client.get(f"/v1/assets/{asset_id}/read-url", headers=stranger)).status_code == 404
    assert (await client.delete(f"/v1/assets/{asset_id}", headers=stranger)).status_code == 404
    invalid_binding = await client.patch(f"/v1/personas/{persona['id']}", headers=stranger,
                                         json={"style_version": 1, "avatar_asset_id": asset_id})
    assert invalid_binding.status_code == 404
    other_persona = await create_persona(client, stranger)
    invalid_binding = await client.patch(f"/v1/personas/{other_persona['id']}", headers=stranger,
                                         json={"style_version": 1, "avatar_asset_id": asset_id})
    assert invalid_binding.status_code == 404
