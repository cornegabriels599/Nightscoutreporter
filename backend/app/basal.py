"""Utilities for converting Nightscout Temp Basal treatments into a step-series."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def parse_temp_basals(
    treatments: List[Dict[str, Any]],
    cutoff: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Parse Nightscout treatments and return temp-basal step series + events.

    Each treatment with eventType == "Temp Basal" has:
      - date (ms epoch) or created_at (ISO string)
      - duration (minutes)
      - rate or absolute (U/hr)

    Returns:
        {
            "series":  [{t: int(ms), rate: float}, ...],   # step-plot points
            "events":  [{t, rate, duration_min}, ...],      # raw events
            "last_event_time": str | None,                  # ISO
            "data_age_seconds": int | None,
        }
    """
    events: List[Dict[str, Any]] = []

    for tx in treatments:
        if tx.get("eventType") != "Temp Basal":
            continue

        # Determine timestamp (ms)
        date_ms = tx.get("date")
        if date_ms is None:
            created = tx.get("created_at")
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    date_ms = int(dt.timestamp() * 1000)
                except (ValueError, TypeError):
                    continue
            else:
                continue

        # Determine rate (prefer 'rate', fall back to 'absolute')
        rate = tx.get("rate")
        if rate is None:
            rate = tx.get("absolute")
        if rate is None:
            continue
        rate = float(rate)

        duration_min = float(tx.get("duration", 0))

        event_dt = datetime.fromtimestamp(date_ms / 1000, tz=timezone.utc)
        if cutoff and event_dt < cutoff:
            continue

        events.append({
            "t": int(date_ms),
            "rate": rate,
            "duration_min": duration_min,
        })

    # Sort chronologically
    events.sort(key=lambda e: e["t"])

    # Build step series: for each event, emit a start point and an end point
    # so a step chart can be drawn.
    series: List[Dict[str, Any]] = []
    for ev in events:
        start_ms = ev["t"]
        end_ms = start_ms + int(ev["duration_min"] * 60 * 1000)
        series.append({"t": start_ms, "rate": ev["rate"]})
        series.append({"t": end_ms, "rate": ev["rate"]})

    # Compute last event time and data age
    now = datetime.now(timezone.utc)
    last_event_time: Optional[str] = None
    data_age_seconds: Optional[int] = None

    if events:
        last_ev = events[-1]
        last_end_ms = last_ev["t"] + int(last_ev["duration_min"] * 60 * 1000)
        last_dt = datetime.fromtimestamp(last_end_ms / 1000, tz=timezone.utc)
        last_event_time = last_dt.isoformat()
        data_age_seconds = int((now - last_dt).total_seconds())

    return {
        "series": series,
        "events": events,
        "last_event_time": last_event_time,
        "data_age_seconds": data_age_seconds,
    }
