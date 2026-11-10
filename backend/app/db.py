from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=10)


@asynccontextmanager
async def transaction():
    async with engine.begin() as connection:
        yield connection


async def execute(conn: AsyncConnection, sql: str, params: dict[str, Any] | None = None):
    return await conn.execute(text(sql), params or {})


async def fetch_one(conn: AsyncConnection, sql: str, params: dict[str, Any] | None = None) -> dict | None:
    row = (await execute(conn, sql, params)).mappings().first()
    return dict(row) if row is not None else None


async def fetch_all(conn: AsyncConnection, sql: str, params: dict[str, Any] | None = None) -> list[dict]:
    return [dict(row) for row in (await execute(conn, sql, params)).mappings().all()]
