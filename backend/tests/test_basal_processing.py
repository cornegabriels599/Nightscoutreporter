"""Tests for basal_processing module."""

from datetime import datetime, timezone

from app.basal_processing import (
    basal_data_age,
    build_step_series,
    compute_loop_activity,
    parse_temp_basals,
)


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def test_parse_temp_basals_filters():
    treatments = [
        {"eventType": "Temp Basal", "date": 1000, "rate": 0.5, "duration": 30},
        {"eventType": "Bolus", "date": 2000, "amount": 5},
        {"eventType": "Temp Basal", "date": 3000, "absolute": 0.8, "duration": 15},
        {"eventType": "Temp Basal"},  # no date -> skip
    ]
    result = parse_temp_basals(treatments)
    assert len(result) == 2
    assert result[0]["rate"] == 0.5
    assert result[1]["rate"] == 0.8


def test_build_step_series():
    events = [
        {"t": 1000, "rate": 0.5, "duration_min": 30},
        {"t": 2000, "rate": 0.8, "duration_min": 15},
    ]
    series = build_step_series(events)
    # 2 events * 2 points each = 4
    assert len(series) == 4
    assert series[0]["rate"] == 0.5
    assert series[2]["rate"] == 0.8


def test_basal_data_age_empty():
    result = basal_data_age([])
    assert result["last_event_time"] is None
    assert result["data_age_seconds"] is None


def test_compute_loop_activity_basic():
    now = _now_ms()
    # One event spanning 2 hours: 120 minutes at rate 1.0
    events = [
        {"t": now - 120 * 60 * 1000, "rate": 1.0, "duration_min": 120},
    ]
    result = compute_loop_activity(events, days=1)
    assert len(result["hours"]) == 24
    assert len(result["percent_temp"]) == 24
    assert len(result["mean_rate"]) == 24
    # At least some hours should have > 0 percent
    assert any(p > 0 for p in result["percent_temp"])
