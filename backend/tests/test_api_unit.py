from io import BytesIO

import pytest
from PIL import Image

from app.config import settings
from app.errors import AppError
from app.schemas.requests import PhoneRequest
from app.services.body_limit import UploadBodyLimit
from app.services.common import decode_cursor, encode_cursor
from app.services.storage import clean_avatar


def test_animated_avatar_is_rejected_even_with_supported_format():
    frames = [Image.new("RGB", (10, 10), color) for color in ("red", "blue")]
    raw = BytesIO()
    frames[0].save(raw, format="PNG", save_all=True, append_images=frames[1:], duration=100, loop=0)
    with pytest.raises(AppError, match="静态图片") as exc:
        clean_avatar(raw.getvalue())
    assert exc.value.code == "ANIMATED_IMAGE"


async def test_chunked_body_limit_stops_before_downstream_accepts_oversized_data(monkeypatch):
    monkeypatch.setattr(settings, "max_avatar_bytes", 10)
    accepted = []
    events = iter([{"type": "http.request", "body": b"x" * 32_768, "more_body": True},
                   {"type": "http.request", "body": b"x" * 32_779, "more_body": False}])

    async def receive():
        return next(events)

    async def consumer(scope, incoming, send):
        while True:
            event = await incoming()
            accepted.append(event["body"])
            if not event.get("more_body"):
                break

    with pytest.raises(AppError) as exc:
        await UploadBodyLimit(consumer)({"type": "http", "path": "/v1/assets/avatar"}, receive, None)
    assert exc.value.status_code == 413
    assert len(accepted) == 1


def test_cursor_round_trip_and_rejects_malformed_input():
    from datetime import UTC, datetime
    from uuid import uuid4

    row = {"created_at": datetime.now(UTC), "id": uuid4()}
    assert decode_cursor(encode_cursor(row)) == {"cursor_time": row["created_at"], "cursor_id": row["id"]}
    for cursor in ("invalid", "a" * 201, "!@#$"):
        with pytest.raises(AppError):
            decode_cursor(cursor)


def test_phone_normalization_uses_ascii_e164():
    assert PhoneRequest(phone="13800000001").phone == "+8613800000001"
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PhoneRequest(phone="+86١٣٨٠٠٠٠٠٠٠١")
