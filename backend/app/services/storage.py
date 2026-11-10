import hmac
import io
import time
import warnings
from pathlib import Path
from uuid import UUID

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings
from app.errors import AppError
from app.services.security import keyed_hash


def clean_avatar(raw: bytes) -> bytes:
    if not raw or len(raw) > settings.max_avatar_bytes:
        raise AppError(413, "UPLOAD_TOO_LARGE", "图片最大为5MB。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as original:
                if original.format not in {"JPEG", "PNG", "WEBP"}:
                    raise AppError(415, "UNSUPPORTED_IMAGE", "请选择JPEG、PNG或WebP图片。")
                if getattr(original, "is_animated", False) or getattr(original, "n_frames", 1) > 1:
                    raise AppError(415, "ANIMATED_IMAGE", "请选择静态图片。")
                if original.width * original.height > settings.max_avatar_pixels:
                    raise AppError(413, "IMAGE_TOO_LARGE", "图片像素过大，请缩小后重试。")
                original.load()
                image = ImageOps.exif_transpose(original).convert("RGB")
                image.thumbnail((1024, 1024))
                output = io.BytesIO()
                image.save(output, "JPEG", quality=88, optimize=True)
                return output.getvalue()
    except AppError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        raise AppError(415, "INVALID_IMAGE", "图片无法读取，请选择另一张图片。") from None


def storage_path(object_key: str) -> Path:
    root = settings.local_storage_dir.resolve()
    path = (root / object_key).resolve()
    if not path.is_relative_to(root) or path == root:
        raise AppError(400, "INVALID_STORAGE_KEY", "文件路径无效。")
    return path


def signed_read_url(asset_id: UUID):
    expires = int(time.time()) + settings.signed_url_seconds
    signature = keyed_hash(f"{asset_id}:{expires}", "asset-url")
    return {"url": f"/v1/assets/{asset_id}/content?expires={expires}&signature={signature}",
            "expires_in": settings.signed_url_seconds}


def verify_signature(asset_id: UUID, expires: int, signature: str):
    now = int(time.time())
    expected = keyed_hash(f"{asset_id}:{expires}", "asset-url")
    if expires < now or expires > now + settings.signed_url_seconds + 30 or \
            not hmac.compare_digest(signature, expected):
        raise AppError(403, "ASSET_URL_EXPIRED", "图片地址已失效，请刷新。")
