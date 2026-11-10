from uuid import UUID

from fastapi import APIRouter, Depends

from app.db import fetch_one, transaction
from app.errors import not_found
from app.services.security import current_user

router = APIRouter(prefix="/operations", tags=["operations"])


@router.get("/{operation_id}")
async def operation(operation_id: UUID, owner: UUID = Depends(current_user)):
    async with transaction() as conn:
        row = await fetch_one(conn, """SELECT id,kind,state,attempts,max_attempts,error_code,created_at,updated_at
            FROM jobs WHERE id=:id AND owner_id=:owner AND kind='purge_data'""", {"id": operation_id, "owner": owner})
    if not row:
        raise not_found()
    return {**row, "operation_id": row["id"], "status": row["state"]}
