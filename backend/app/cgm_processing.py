"""CGM data parsing, gap detection, metrics, and resampling."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional, Tuple


# ── Parsing ───────────────────────────────────────────────────────

def parse_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert raw Nightscout entries to sorted [{t(ms), sgv(int)}]."""
    points: List[Dict[str, Any]] = []
    for entry in entries:
        sgv = entry.get("sgv")
        date_ms = entry.get("date")
        if sgv is None or date_ms is None:
            continue
        points.append({"t": int(date_ms), "sgv": int(sgv)})
    points.sort(key=lambda p: p["t"])
    return points


def filter_window(points: List[Dict[str, Any]], hours: int) -> List[Dict[str, Any]]:
    """Keep only points within the last *hours*."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_ms = int(cutoff.timestamp() * 1000)
    return [p for p in points if p["t"] >= cutoff_ms]


def filter_range(
    points: List[Dict[str, Any]],
    start: datetime,
    end: datetime,
) -> List[Dict[str, Any]]:
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    return [p for p in points if start_ms <= p["t"] <= end_ms]


# ── Gap detection ─────────────────────────────────────────────────

GAP_THRESHOLD_SECONDS = 720  # 12 minutes


def detect_gaps(points: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Return list of [{start(iso), end(iso)}] where dt > 12 min."""
    gaps: List[Dict[str, str]] = []
    for i in range(1, len(points)):
        dt_sec = (points[i]["t"] - points[i - 1]["t"]) / 1000
        if dt_sec > GAP_THRESHOLD_SECONDS:
            gaps.append({
                "start": _ms_to_iso(points[i - 1]["t"]),
                "end": _ms_to_iso(points[i]["t"]),
            })
    return gaps


# ── Metrics ───────────────────────────────────────────────────────

STALE_THRESHOLD_SECONDS = 600  # 10 minutes


def compute_metrics(points: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Compute CGM summary metrics from point list."""
    empty: Dict[str, Optional[float]] = {
        "mean": None, "sd": None, "cv": None,
        "tir": None, "tbr": None, "tar": None,
        "last": None, "delta_15m": None, "delta_30m": None,
        "data_age_seconds": None, "coverage_percent": None,
    }
    if not points:
        return empty

    values = [p["sgv"] for p in points if p.get("sgv") is not None]
    if not values:
        return empty

    avg = mean(values)
    sd = pstdev(values) if len(values) > 1 else 0.0
    cv = round((sd / avg) * 100, 1) if avg else None
    total = len(values)
    tir = round(sum(1 for v in values if 70 <= v <= 180) / total * 100, 1)
    tbr = round(sum(1 for v in values if v < 70) / total * 100, 1)
    tar = round(sum(1 for v in values if v > 180) / total * 100, 1)

    last_sgv = values[-1]
    delta_15m = _find_delta(points, 15)
    delta_30m = _find_delta(points, 30)

    now = datetime.now(timezone.utc)
    last_ms = points[-1]["t"]
    last_dt = datetime.fromtimestamp(last_ms / 1000, tz=timezone.utc)
    data_age = int((now - last_dt).total_seconds())

    # Coverage: expected 1 reading / 5 min
    span_minutes = (points[-1]["t"] - points[0]["t"]) / 1000 / 60
    expected = max(span_minutes / 5, 1)
    coverage = round(min(total / expected * 100, 100), 1)

    return {
        "mean": round(avg, 1),
        "sd": round(sd, 1),
        "cv": cv,
        "tir": tir,
        "tbr": tbr,
        "tar": tar,
        "last": last_sgv,
        "delta_15m": delta_15m,
        "delta_30m": delta_30m,
        "data_age_seconds": data_age,
        "coverage_percent": coverage,
    }


# ── Resampling ────────────────────────────────────────────────────

def resample_5min(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Resample to a 5-minute grid (average per bucket)."""
    if not points:
        return []
    buckets: Dict[int, List[int]] = {}
    for p in points:
        bucket_ms = (p["t"] // 300_000) * 300_000  # floor to 5 min
        buckets.setdefault(bucket_ms, []).append(p["sgv"])
    result = []
    for t_ms in sorted(buckets):
        result.append({"t": t_ms, "sgv": round(mean(buckets[t_ms]))})
    return result


# ── Helpers ───────────────────────────────────────────────────────

def _ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _find_delta(points: List[Dict[str, Any]], minutes: int) -> Optional[int]:
    if len(points) < 2:
        return None
    latest = points[-1]
    target_ms = latest["t"] - minutes * 60 * 1000
    closest = min(points, key=lambda p: abs(p["t"] - target_ms))
    # Only valid if within 3 minutes of target
    if abs(closest["t"] - target_ms) > 3 * 60 * 1000:
        return None
    return latest["sgv"] - closest["sgv"]
