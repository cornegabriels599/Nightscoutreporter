"""Ambulatory Glucose Profile (AGP) — percentile bands per 5-min bucket."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _percentile(values: List[int], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    rank = (len(s) - 1) * p
    lo = int(rank)
    hi = min(lo + 1, len(s) - 1)
    w = rank - lo
    return s[lo] * (1 - w) + s[hi] * w


def build_agp(
    points: List[Dict[str, Any]],
    step_minutes: int = 5,
) -> Dict[str, Any]:
    """Build AGP from points [{t(ms), sgv}].

    Returns:
        {
            "bucket_minutes": 5,
            "series": [{"minute_of_day": 0, "p10": .., "p50": .., "p90": ..}, ...]
        }
    """
    buckets: Dict[int, List[int]] = defaultdict(list)
    for p in points:
        dt = datetime.fromtimestamp(p["t"] / 1000, tz=timezone.utc)
        mod = dt.hour * 60 + dt.minute
        bucket = mod - (mod % step_minutes)
        buckets[bucket].append(p["sgv"])

    series = []
    for minute in range(0, 24 * 60, step_minutes):
        vals = buckets.get(minute, [])
        if vals:
            series.append({
                "minute_of_day": minute,
                "p10": round(_percentile(vals, 0.10), 1),
                "p25": round(_percentile(vals, 0.25), 1),
                "p50": round(_percentile(vals, 0.50), 1),
                "p75": round(_percentile(vals, 0.75), 1),
                "p90": round(_percentile(vals, 0.90), 1),
            })
        else:
            series.append({
                "minute_of_day": minute,
                "p10": None, "p25": None, "p50": None, "p75": None, "p90": None,
            })

    return {"bucket_minutes": step_minutes, "series": series}
