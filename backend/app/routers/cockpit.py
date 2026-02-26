"""Combined cockpit (/me/cockpit) and insights (/me/insights) endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.agp import build_agp
from app.auth import get_current_user
from app.basal_processing import (
    basal_data_age,
    build_step_series,
    compute_loop_activity,
    parse_temp_basals,
)
from app.cache import get_cached_payload, set_cached_payload
from app.cgm_processing import (
    compute_metrics,
    detect_gaps,
    filter_window,
    parse_entries,
    resample_5min,
)
from app.crypto import decrypt_token
from app.db import get_db
from app.insights import compute_dayparts, compute_hypo_heatmap
from app.models import NightscoutConnection, User
from app.nightscout import fetch_entries, fetch_treatments

router = APIRouter(prefix="/me", tags=["cockpit"])

STALE_CGM_SECONDS = 600  # 10 min
STALE_BASAL_SECONDS = 600

COCKPIT_CACHE_TTL = 30  # seconds
INSIGHTS_CACHE_TTL = 300  # seconds


# ── helpers ───────────────────────────────────────────────────────

def _get_connection(db: Session, user_id: int) -> NightscoutConnection:
    conn = (
        db.query(NightscoutConnection)
        .filter(NightscoutConnection.user_id == user_id)
        .first()
    )
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nightscout not connected",
        )
    return conn


# ── /me/cockpit ───────────────────────────────────────────────────

@router.get("/cockpit")
def get_cockpit(
    hours: int = Query(12, ge=3, le=48),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    cache_key = f"cockpit:{hours}"
    cached = get_cached_payload(db, user.id, cache_key)
    if cached:
        return cached

    connection = _get_connection(db, user.id)
    token = decrypt_token(connection.token_encrypted)
    now = datetime.now(timezone.utc)

    # ---- CGM ---------------------------------------------------
    cgm_count = max(8000, hours * 15)
    try:
        raw_entries = fetch_entries(connection.url, token, count=cgm_count)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Nightscout unreachable",
        ) from exc

    all_points = parse_entries(raw_entries)
    points = filter_window(all_points, hours)
    gaps = detect_gaps(points)
    metrics = compute_metrics(points)

    cgm_status = "ok"
    if metrics.get("data_age_seconds") and metrics["data_age_seconds"] > STALE_CGM_SECONDS:
        cgm_status = "stale"

    cgm_block: Dict[str, Any] = {
        "points": points,
        "gaps": gaps,
        "metrics": metrics,
        "status": cgm_status,
    }

    # ---- Basal -------------------------------------------------
    basal_count = max(2000, hours * 20)
    basal_block: Dict[str, Any] = {
        "series": [],
        "last_event_time": None,
        "data_age_seconds": None,
    }
    try:
        raw_treatments = fetch_treatments(connection.url, token, count=basal_count)
        cutoff = now - timedelta(hours=hours)
        events = parse_temp_basals(raw_treatments, cutoff=cutoff)
        series = build_step_series(events)
        age_info = basal_data_age(events)
        basal_block = {
            "series": series,
            "last_event_time": age_info["last_event_time"],
            "data_age_seconds": age_info["data_age_seconds"],
        }
    except Exception:
        pass  # basal is best-effort; CGM is primary

    payload: Dict[str, Any] = {
        "server_time": now.isoformat(),
        "cgm": cgm_block,
        "basal": basal_block,
    }
    set_cached_payload(db, user.id, cache_key, payload, ttl_seconds=COCKPIT_CACHE_TTL)
    return payload


# ── /me/insights ──────────────────────────────────────────────────

@router.get("/insights")
def get_insights(
    days: int = Query(14, ge=7, le=28),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    cache_key = f"insights:{days}"
    cached = get_cached_payload(db, user.id, cache_key)
    if cached:
        return cached

    connection = _get_connection(db, user.id)
    token = decrypt_token(connection.token_encrypted)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    # ---- CGM ---------------------------------------------------
    cgm_count = max(25000, days * 300)
    try:
        raw_entries = fetch_entries(connection.url, token, count=cgm_count)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Nightscout unreachable",
        ) from exc

    all_points = parse_entries(raw_entries)
    cutoff_ms = int(cutoff.timestamp() * 1000)
    points = [p for p in all_points if p["t"] >= cutoff_ms]
    resampled = resample_5min(points)

    metrics = compute_metrics(points)
    summary = {
        "coverage_percent": metrics.get("coverage_percent"),
        "mean": metrics.get("mean"),
        "sd": metrics.get("sd"),
        "cv_percent": metrics.get("cv"),
        "tir_percent": metrics.get("tir"),
        "tbr_percent": metrics.get("tbr"),
        "tar_percent": metrics.get("tar"),
    }

    agp = build_agp(resampled)
    hypo_heatmap = compute_hypo_heatmap(resampled)
    dayparts = compute_dayparts(resampled)

    # ---- Basal (loop activity) --------------------------------
    treatment_count = max(5000, days * 400)
    loop_activity: Dict[str, Any] = {"hours": list(range(24)), "percent_temp": [0.0] * 24, "mean_rate": [0.0] * 24}
    try:
        raw_treatments = fetch_treatments(connection.url, token, count=treatment_count)
        events = parse_temp_basals(raw_treatments, cutoff=cutoff)
        loop_activity = compute_loop_activity(events, days=days)
    except Exception:
        pass  # best-effort

    payload: Dict[str, Any] = {
        "server_time": now.isoformat(),
        "summary": summary,
        "agp": agp,
        "hypo_heatmap": hypo_heatmap,
        "dayparts": dayparts,
        "loop_activity": loop_activity,
    }
    set_cached_payload(db, user.id, cache_key, payload, ttl_seconds=INSIGHTS_CACHE_TTL)
    return payload
