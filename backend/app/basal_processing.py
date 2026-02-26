"""Temp-basal treatment parsing, step-series, and loop-activity aggregation."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


# ── Parsing ───────────────────────────────────────────────────────

def parse_temp_basals(
    treatments: List[Dict[str, Any]],
    cutoff: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Filter and parse Temp Basal treatments -> [{t(ms), rate, duration_min}]."""
    events: List[Dict[str, Any]] = []

    for tx in treatments:
        if tx.get("eventType") != "Temp Basal":
            continue

        date_ms = tx.get("date")
        if date_ms is None:
            created = tx.get("created_at")
            if created:
                try:
                    dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                    date_ms = int(dt.timestamp() * 1000)
                except (ValueError, TypeError):
                    continue
            else:
                continue

        rate = tx.get("rate")
        if rate is None:
            rate = tx.get("absolute")
        if rate is None:
            continue
        rate = float(rate)

        duration_min = float(tx.get("duration", 0))

        if cutoff:
            event_dt = datetime.fromtimestamp(date_ms / 1000, tz=timezone.utc)
            if event_dt < cutoff:
                continue

        events.append({"t": int(date_ms), "rate": rate, "duration_min": duration_min})

    events.sort(key=lambda e: e["t"])
    return events


# ── Step series ───────────────────────────────────────────────────

def build_step_series(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert events to step-series [{t(ms), rate}] for plotting."""
    series: List[Dict[str, Any]] = []
    for ev in events:
        start_ms = ev["t"]
        end_ms = start_ms + int(ev["duration_min"] * 60 * 1000)
        series.append({"t": start_ms, "rate": ev["rate"]})
        series.append({"t": end_ms, "rate": ev["rate"]})
    return series


def basal_data_age(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute last_event_time and data_age_seconds."""
    if not events:
        return {"last_event_time": None, "data_age_seconds": None}
    now = datetime.now(timezone.utc)
    last_ev = events[-1]
    last_end_ms = last_ev["t"] + int(last_ev["duration_min"] * 60 * 1000)
    last_dt = datetime.fromtimestamp(last_end_ms / 1000, tz=timezone.utc)
    return {
        "last_event_time": last_dt.isoformat(),
        "data_age_seconds": int((now - last_dt).total_seconds()),
    }


# ── Loop-activity aggregation ─────────────────────────────────────

def compute_loop_activity(
    events: List[Dict[str, Any]],
    days: int = 14,
) -> Dict[str, Any]:
    """Per hour of day (0-23): percent of time with temp basal + mean temp rate.

    Uses duration-weighted overlap with each clock-hour across *days* days.
    """
    # Accumulators per hour
    total_minutes_per_hour = [0.0] * 24   # total temp-basal minutes overlapping this hour
    weighted_rate_per_hour = [0.0] * 24   # sum(rate * overlap_minutes)

    for ev in events:
        start_dt = datetime.fromtimestamp(ev["t"] / 1000, tz=timezone.utc)
        end_dt = start_dt + timedelta(minutes=ev["duration_min"])

        # Walk through each clock-hour that the event overlaps
        cursor = start_dt.replace(minute=0, second=0, microsecond=0)
        while cursor < end_dt:
            next_hour = cursor + timedelta(hours=1)
            overlap_start = max(cursor, start_dt)
            overlap_end = min(next_hour, end_dt)
            overlap_min = max((overlap_end - overlap_start).total_seconds() / 60, 0)

            h = cursor.hour
            total_minutes_per_hour[h] += overlap_min
            weighted_rate_per_hour[h] += ev["rate"] * overlap_min
            cursor = next_hour

    # Normalize: total available minutes per hour = days * 60
    available = max(days * 60, 1)
    percent_temp = [round(m / available * 100, 1) for m in total_minutes_per_hour]
    mean_rate = [
        round(weighted_rate_per_hour[h] / total_minutes_per_hour[h], 2)
        if total_minutes_per_hour[h] > 0 else 0.0
        for h in range(24)
    ]

    return {
        "hours": list(range(24)),
        "percent_temp": percent_temp,
        "mean_rate": mean_rate,
    }
