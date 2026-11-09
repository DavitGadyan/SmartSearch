import hashlib
import hmac

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def require_admin(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Admin/analytics routes accept the env ADMIN_API_KEY or any key stored in api_keys."""
    if not x_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-API-Key header")
    if hmac.compare_digest(x_api_key, settings.admin_api_key):
        return "env-admin"

    from app.models import ApiKey  # local import to avoid cycles

    row = await db.scalar(select(ApiKey).where(ApiKey.key_hash == hash_key(x_api_key)))
    if row is None or not row.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid API key")
    return row.name
