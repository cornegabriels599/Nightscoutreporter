from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.basal import parse_temp_basals
from app.cache import get_cached_payload, set_cached_payload
from app.crypto import decrypt_token
from app.db import get_db
from app.models import NightscoutConnection, User
from app.nightscout import fetch_treatments


router = APIRouter(prefix="/me/basal", tags=["basal"])


def _get_connection(db: Session, user_id: int) -> NightscoutConnection:
    connection = (
        db.query(NightscoutConnection)
        .filter(NightscoutConnection.user_id == user_id)
        .first()
    )
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nightscout not connected",
        )
    return connection


@router.get("/window")
def get_basal_window(
    hours: int = Query(12, ge=1, le=168),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cache_key = f"basal:{hours}"
    cached = get_cached_payload(db, user.id, cache_key)
    if cached:
        return cached

    connection = _get_connection(db, user.id)
    token = decrypt_token(connection.token_encrypted)

    count = max(2000, hours * 20)
    try:
        treatments = fetch_treatments(connection.url, token, count=count)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Nightscout unreachable",
        ) from exc

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = parse_temp_basals(treatments, cutoff=cutoff)

    payload = {
        "series": result["series"],
        "events": result["events"],
        "last_event_time": result["last_event_time"],
        "data_age_seconds": result["data_age_seconds"],
        "server_time": datetime.now(timezone.utc).isoformat(),
    }
    set_cached_payload(db, user.id, cache_key, payload)
    return payload
