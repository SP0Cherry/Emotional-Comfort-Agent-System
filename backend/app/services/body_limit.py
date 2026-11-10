from app.config import settings
from app.errors import AppError


class UploadBodyLimit:
    """Bound multipart data before Starlette can spool an unbounded upload to disk."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] != "/v1/assets/avatar":
            return await self.app(scope, receive, send)
        size = 0
        limit = settings.max_avatar_bytes + 64 * 1024  # Form metadata and boundaries.

        async def limited_receive():
            nonlocal size
            event = await receive()
            if event["type"] == "http.request":
                size += len(event.get("body", b""))
                if size > limit:
                    raise AppError(413, "UPLOAD_TOO_LARGE", "图片最大为5MB。")
            return event

        await self.app(scope, limited_receive, send)
