from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import CachedPayload


def get_cached_payload(db: Session, user_id: int, cache_key: str) -> Optional[dict]:
    now = datetime.now(timezone.utc)
    cached = (
        db.query(CachedPayload)
        .filter(
            CachedPayload.user_id == user_id,
            CachedPayload.cache_key == cache_key,
            CachedPayload.expires_at > now,
        )
        .first()
    )
    return cached.payload if cached else None


def set_cached_payload(
    db: Session,
    user_id: int,
    cache_key: str,
    payload: Any,
    ttl_seconds: Optional[int] = None,
) -> None:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=ttl_seconds or settings.cache_ttl_seconds)
    cached = (
        db.query(CachedPayload)
        .filter(CachedPayload.user_id == user_id, CachedPayload.cache_key == cache_key)
        .first()
    )
    if cached:
        cached.payload = payload
        cached.fetched_at = now
        cached.expires_at = expires_at
    else:
        cached = CachedPayload(
            user_id=user_id,
            cache_key=cache_key,
            payload=payload,
            fetched_at=now,
            expires_at=expires_at,
        )
        db.add(cached)
    db.commit()
