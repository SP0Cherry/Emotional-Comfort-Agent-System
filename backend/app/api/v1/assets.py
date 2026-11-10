from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.db import execute, fetch_one, transaction
from app.errors import AppError, not_found
from app.services.security import current_user, rate_limit
from app.services.storage import clean_avatar, signed_read_url, storage_path, verify_signature

router = APIRouter(prefix="/assets", tags=["assets"])


@router.post("/avatar", status_code=201)
async def upload_avatar(file: UploadFile = File(...), owner: UUID = Depends(current_user)):
    await rate_limit("upload", str(owner), 30, 3600)
    try:
        raw = await file.read(settings.max_avatar_bytes + 1)
    finally:
        await file.close()
    data = await run_in_threadpool(clean_avatar, raw)
    asset_id = uuid4()
    object_key = f"avatars/{owner}/{asset_id}.jpg"
    path = storage_path(object_key)

    def write():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as output:
            output.write(data)

    await run_in_threadpool(write)
    try:
        async with transaction() as conn:
            await execute(conn, """INSERT INTO assets(id,owner_id,object_key,purpose,mime_type,size_bytes,status)
                VALUES (:id,:owner,:key,'avatar','image/jpeg',:size,'ready')""",
                          {"id": asset_id, "owner": owner, "key": object_key, "size": len(data)})
    except Exception:
        await run_in_threadpool(path.unlink, True)
        raise
    return {"asset_id": asset_id, "mime_type": "image/jpeg", "size_bytes": len(data)}


@router.get("/{asset_id}/read-url")
async def read_url(asset_id: UUID, owner: UUID = Depends(current_user)):
    async with transaction() as conn:
        asset = await fetch_one(conn, """SELECT id FROM assets WHERE id=:id AND owner_id=:owner
            AND status='ready' AND (expires_at IS NULL OR expires_at>now())""", {"id": asset_id, "owner": owner})
    if not asset:
        raise not_found()
    return signed_read_url(asset_id)


@router.get("/{asset_id}/content", include_in_schema=False)
async def content(asset_id: UUID, expires: int = Query(...), signature: str = Query(..., max_length=128)):
    verify_signature(asset_id, expires, signature)
    async with transaction() as conn:
        asset = await fetch_one(conn, """SELECT object_key FROM assets WHERE id=:id AND status='ready'
            AND (expires_at IS NULL OR expires_at>now())""", {"id": asset_id})
    if not asset:
        raise not_found()
    path = storage_path(asset["object_key"])
    if not path.is_file():
        raise not_found()
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=60",
                        "X-Content-Type-Options": "nosniff", "Content-Disposition": "inline"})


@router.delete("/{asset_id}", status_code=202)
async def delete_asset(asset_id: UUID, owner: UUID = Depends(current_user)):
    async with transaction() as conn:
        asset = await fetch_one(conn, "SELECT * FROM assets WHERE id=:id AND owner_id=:owner FOR UPDATE",
                                {"id": asset_id, "owner": owner})
        if not asset:
            raise not_found()
        bound = await fetch_one(conn, "SELECT id FROM personas WHERE avatar_asset_id=:id AND owner_id=:owner",
                                {"id": asset_id, "owner": owner})
        if bound:
            raise AppError(409, "ASSET_IN_USE", "请先解除人物头像关联。")
        if asset["status"] != "deleted":
            await execute(conn, "UPDATE assets SET status='deleting' WHERE id=:id", {"id": asset_id})
        job = await fetch_one(conn, """INSERT INTO jobs(owner_id,kind,target_id,dedup_key,max_attempts)
            VALUES (:owner,'purge_data',:id,:dedup,3) ON CONFLICT(dedup_key)
            DO UPDATE SET dedup_key=EXCLUDED.dedup_key RETURNING id,state""",
                              {"owner": owner, "id": asset_id, "dedup": f"purge:asset:{asset_id}"})
    return {"operation_id": job["id"], "status": job["state"]}
