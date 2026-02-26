from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.agp import build_agp
from app.auth import get_current_user
from app.cache import get_cached_payload, set_cached_payload
from app.crypto import decrypt_token
from app.db import get_db
from app.metrics import compute_metrics
from app.models import NightscoutConnection, User
from app.nightscout import fetch_entries


router = APIRouter(prefix="/me/cgm", tags=["cgm"])


def _parse_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, int]]:
    points: List[Dict[str, int]] = []
    for entry in entries:
        sgv = entry.get("sgv")
        date_ms = entry.get("date")
        if sgv is None or date_ms is None:
            continue
        points.append({"t": int(date_ms), "sgv": int(sgv)})
    points.sort(key=lambda p: p["t"])
    return points


def _get_connection(db: Session, user_id: int) -> NightscoutConnection:
    connection = (
        db.query(NightscoutConnection).filter(NightscoutConnection.user_id == user_id).first()
    )
    if not connection:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nightscout not connected")
    return connection


STALE_THRESHOLD_SECONDS = 600  # 10 minutes


@router.get("/window")
def get_window(
    hours: int = Query(3, ge=3, le=168),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cache_key = f"window:{hours}"
    cached = get_cached_payload(db, user.id, cache_key)
    if cached:
        return cached

    connection = _get_connection(db, user.id)
    token = decrypt_token(connection.token_encrypted)

    # Scale count to cover the requested window (~12 readings/hour for 5-min CGM)
    count = max(8000, hours * 15)
    try:
        entries = fetch_entries(connection.url, token, count=count)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Nightscout unreachable") from exc

    points = _parse_entries(entries)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    filtered = [p for p in points if datetime.fromtimestamp(p["t"] / 1000, tz=timezone.utc) >= cutoff]
    metrics = compute_metrics(filtered)

    now = datetime.now(timezone.utc)
    last_entry_time: Optional[str] = None
    data_age_seconds: Optional[int] = None
    data_status = "ok"

    if filtered:
        last_ts = max(p["t"] for p in filtered)
        last_entry_dt = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)
        last_entry_time = last_entry_dt.isoformat()
        data_age_seconds = int((now - last_entry_dt).total_seconds())
        if data_age_seconds > STALE_THRESHOLD_SECONDS:
            data_status = "stale"

    payload = {
        "points": filtered,
        "metrics": metrics,
        "server_time": now.isoformat(),
        "last_entry_time": last_entry_time,
        "data_age_seconds": data_age_seconds,
        "status": data_status,
    }
    set_cached_payload(db, user.id, cache_key, payload)
    return payload


@router.get("/report")
def get_report(
    days: int = Query(14, ge=1, le=31),
    start: Optional[str] = None,
    end: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if start and end:
        try:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format") from exc
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
    else:
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=days)

    hours = int((end_dt - start_dt).total_seconds() / 3600)
    cache_key = f"report:{start_dt.isoformat()}:{end_dt.isoformat()}"
    cached = get_cached_payload(db, user.id, cache_key)
    if cached:
        return cached

    connection = _get_connection(db, user.id)
    token = decrypt_token(connection.token_encrypted)
    try:
        entries = fetch_entries(connection.url, token, count=10000)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Nightscout unreachable") from exc

    points = _parse_entries(entries)
    filtered = [
        p
        for p in points
        if start_dt
        <= datetime.fromtimestamp(p["t"] / 1000, tz=timezone.utc)
        <= end_dt
    ]
    metrics = compute_metrics(filtered)
    expected_points = max(hours * 12, 1)
    uptime = round((len(filtered) / expected_points) * 100, 1)
    agp = build_agp(filtered)
    payload = {
        "points": filtered,
        "metrics": metrics,
        "agp": agp,
        "uptime": uptime,
        "range": {"start": start_dt.isoformat(), "end": end_dt.isoformat()},
        "server_time": datetime.now(timezone.utc).isoformat(),
    }
    set_cached_payload(db, user.id, cache_key, payload)
    return payload
