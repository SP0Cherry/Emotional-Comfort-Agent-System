"""Integration tests use a dedicated real PostgreSQL/pgvector test database."""
import os
import asyncio
import sys

import httpx
import pytest
import pytest_asyncio

if sys.platform == "win32":
    # psycopg async connections cannot run on the Windows Proactor loop.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


test_database = os.environ.get("TEST_DATABASE_URL")
if test_database:
    # Never truncate a normal development or production database by accident.
    from sqlalchemy.engine import make_url

    database_name = make_url(test_database).database or ""
    if not database_name.endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL database name must end with _test")
    os.environ["DATABASE_URL"] = test_database
    os.environ["APP_ENV"] = "development"
    os.environ["PROVIDER_MODE"] = "mock"


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    if not test_database:
        pytest.skip("Set TEST_DATABASE_URL to a migrated PostgreSQL/pgvector *_test database")
    from app.config import settings
    from app.db import engine, execute, transaction
    from app.main import app

    monkeypatch.setattr(settings, "local_storage_dir", tmp_path)
    async with transaction() as conn:
        await execute(conn, "TRUNCATE users, otp_challenges, rate_limit_counters CASCADE")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as session:
        yield session
    await engine.dispose()


async def login(client, phone="13800000001"):
    response = await client.post("/v1/auth/otp/request", json={"phone": phone})
    assert response.status_code == 200, response.text
    challenge = response.json()
    response = await client.post("/v1/auth/otp/verify", json={
        "phone": phone, "code": challenge["development_code"], "challenge_id": challenge["challenge_id"],
    })
    assert response.status_code == 200, response.text
    tokens = response.json()
    return {"Authorization": "Bearer " + tokens["access_token"]}, tokens


@pytest_asyncio.fixture
async def account(client):
    return await login(client)
