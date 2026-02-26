"""Insights aggregations: hypo heatmap, daypart analysis."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List


# ── Hypo heatmap ──────────────────────────────────────────────────

HYPO_THRESHOLD = 70  # mg/dL


def compute_hypo_heatmap(
    points: List[Dict[str, Any]],
    step_minutes: int = 5,
) -> Dict[str, Any]:
    """Minutes < 70 mg/dL per calendar day × hour, using 5-min grid.

    Returns:
        {
            "days": ["YYYY-MM-DD", ...],
            "hours": [0..23],
            "values": [[min_h0, min_h1, ..., min_h23], ...]   # per day
        }
    """
    # Bucket: (date_str, hour) -> count of hypo readings on 5-min grid
    buckets: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))

    for p in points:
        if p["sgv"] >= HYPO_THRESHOLD:
            continue
        dt = datetime.fromtimestamp(p["t"] / 1000, tz=timezone.utc)
        day_str = dt.strftime("%Y-%m-%d")
        buckets[day_str][dt.hour] += 1

    if not buckets:
        return {"days": [], "hours": list(range(24)), "values": []}

    days_sorted = sorted(buckets.keys())
    values = []
    for day in days_sorted:
        row = [buckets[day].get(h, 0) * step_minutes for h in range(24)]
        values.append(row)

    return {
        "days": days_sorted,
        "hours": list(range(24)),
        "values": values,
    }


# ── Daypart analysis ─────────────────────────────────────────────

DAYPARTS = [
    {"name": "Night",     "start": "00:00", "end": "06:00", "start_h": 0,  "end_h": 6},
    {"name": "Morning",   "start": "06:00", "end": "12:00", "start_h": 6,  "end_h": 12},
    {"name": "Afternoon", "start": "12:00", "end": "18:00", "start_h": 12, "end_h": 18},
    {"name": "Evening",   "start": "18:00", "end": "00:00", "start_h": 18, "end_h": 24},
]


def _daypart_stats(values: List[int]) -> Dict[str, Any]:
    if not values:
        return {"tir": None, "tbr": None, "tar": None, "mean": None, "cv": None}
    from statistics import mean as _mean, pstdev
    avg = _mean(values)
    sd = pstdev(values) if len(values) > 1 else 0.0
    n = len(values)
    return {
        "tir": round(sum(1 for v in values if 70 <= v <= 180) / n * 100, 1),
        "tbr": round(sum(1 for v in values if v < 70) / n * 100, 1),
        "tar": round(sum(1 for v in values if v > 180) / n * 100, 1),
        "mean": round(avg, 1),
        "cv": round((sd / avg) * 100, 1) if avg else None,
    }


def compute_dayparts(
    points: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """TIR/TBR/TAR/mean/CV per daypart, overall + weekday + weekend.

    Returns:
        {
            "definition": [{"name","start","end"}, ...],
            "overall":    [{"name","tir","tbr","tar","mean","cv"}, ...],
            "weekday":    [...],
            "weekend":    [...]
        }
    """
    # Bucket per (daypart_index, filter)  filter: "all" | "wd" | "we"
    buckets: Dict[str, Dict[int, List[int]]] = {
        "all": defaultdict(list),
        "wd": defaultdict(list),
        "we": defaultdict(list),
    }

    for p in points:
        dt = datetime.fromtimestamp(p["t"] / 1000, tz=timezone.utc)
        h = dt.hour
        is_weekend = dt.weekday() >= 5  # Sat=5, Sun=6
        for i, dp in enumerate(DAYPARTS):
            if dp["start_h"] <= h < dp["end_h"]:
                buckets["all"][i].append(p["sgv"])
                if is_weekend:
                    buckets["we"][i].append(p["sgv"])
                else:
                    buckets["wd"][i].append(p["sgv"])
                break

    def _build(filter_key: str) -> List[Dict[str, Any]]:
        result = []
        for i, dp in enumerate(DAYPARTS):
            stats = _daypart_stats(buckets[filter_key][i])
            stats["name"] = dp["name"]
            result.append(stats)
        return result

    definition = [{"name": dp["name"], "start": dp["start"], "end": dp["end"]} for dp in DAYPARTS]

    return {
        "definition": definition,
        "overall": _build("all"),
        "weekday": _build("wd"),
        "weekend": _build("we"),
    }
