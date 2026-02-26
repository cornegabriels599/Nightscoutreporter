from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean, pstdev
from typing import Dict, List, Optional


def _ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _find_delta(points: List[Dict[str, int]], minutes: int) -> Optional[int]:
    if len(points) < 2:
        return None
    latest = points[-1]
    latest_time = _ms_to_dt(latest["t"])
    target_time = latest_time - timedelta(minutes=minutes)
    closest = None
    closest_diff = None
    for point in points:
        point_time = _ms_to_dt(point["t"])
        diff = abs((point_time - target_time).total_seconds())
        if closest_diff is None or diff < closest_diff:
            closest_diff = diff
            closest = point
    if not closest:
        return None
    return latest["sgv"] - closest["sgv"]


def compute_metrics(points: List[Dict[str, int]]) -> Dict[str, Optional[float]]:
    if not points:
        return {
            "mean": None,
            "sd": None,
            "cv": None,
            "tir": None,
            "tbr": None,
            "tar": None,
            "last": None,
            "delta_15m": None,
            "delta_30m": None,
        }

    values = [point["sgv"] for point in points if point.get("sgv") is not None]
    if not values:
        return {
            "mean": None,
            "sd": None,
            "cv": None,
            "tir": None,
            "tbr": None,
            "tar": None,
            "last": None,
            "delta_15m": None,
            "delta_30m": None,
        }

    avg = mean(values)
    sd_value = pstdev(values) if len(values) > 1 else 0.0
    cv_value = (sd_value / avg) * 100 if avg else None
    total = len(values)
    tir = sum(1 for v in values if 70 <= v <= 180) / total * 100
    tbr = sum(1 for v in values if v < 70) / total * 100
    tar = sum(1 for v in values if v > 180) / total * 100

    last = values[-1]
    delta_15m = _find_delta(points, 15)
    delta_30m = _find_delta(points, 30)

    return {
        "mean": round(avg, 1),
        "sd": round(sd_value, 1),
        "cv": round(cv_value, 1) if cv_value is not None else None,
        "tir": round(tir, 1),
        "tbr": round(tbr, 1),
        "tar": round(tar, 1),
        "last": last,
        "delta_15m": delta_15m,
        "delta_30m": delta_30m,
    }
