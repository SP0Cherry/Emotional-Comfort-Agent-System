import base64
import json
from datetime import UTC, datetime
from uuid import UUID

from app.db import fetch_one
from app.errors import AppError, not_found


def json_dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


async def owned_persona(conn, owner: UUID, persona_id: UUID, *, lock=False, active=False):
    row = await fetch_one(conn, "SELECT * FROM personas WHERE id=:id AND owner_id=:owner" +
                          (" FOR UPDATE" if lock else " FOR SHARE" if active else ""),
                          {"id": persona_id, "owner": owner})
    if not row:
        raise not_found()
    if active and row["status"] != "active":
        if row["status"] == "resetting":
            raise AppError(409, "CONTEXT_RESETTING", "正在清除该人物的对话与记忆，请稍后重试。")
        raise AppError(409, "PERSONA_UNAVAILABLE", "人物资料正在处理，请稍后重试。")
    return row


def encode_cursor(row, time_key="created_at"):
    return base64.urlsafe_b64encode(f"{row[time_key].isoformat()}|{row['id']}".encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None):
    if cursor is None:
        return {"cursor_time": datetime.max.replace(tzinfo=UTC),
                "cursor_id": UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")}
    try:
        if len(cursor) > 200:
            raise ValueError("long cursor")
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        stamp, value = raw.split("|")
        stamp = datetime.fromisoformat(stamp)
        if stamp.tzinfo is None:
            raise ValueError("missing timezone")
        return {"cursor_time": stamp, "cursor_id": UUID(value)}
    except (ValueError, UnicodeDecodeError):
        raise AppError(400, "INVALID_CURSOR", "分页游标无效。") from None


def paginated(rows, limit, time_key="created_at"):
    more = len(rows) > limit
    items = rows[:limit]
    return {"items": items, "next_cursor": encode_cursor(items[-1], time_key) if more else None}
