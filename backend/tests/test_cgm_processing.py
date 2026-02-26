"""Tests for cgm_processing module."""

from datetime import datetime, timezone

from app.cgm_processing import (
    compute_metrics,
    detect_gaps,
    filter_window,
    parse_entries,
    resample_5min,
)


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def test_parse_entries_filters_invalid():
    raw = [
        {"sgv": 120, "date": 1000},
        {"sgv": None, "date": 2000},
        {"date": 3000},
        {"sgv": 100},
    ]
    result = parse_entries(raw)
    assert len(result) == 1
    assert result[0]["sgv"] == 120


def test_parse_entries_sorted():
    raw = [
        {"sgv": 120, "date": 3000},
        {"sgv": 100, "date": 1000},
        {"sgv": 110, "date": 2000},
    ]
    result = parse_entries(raw)
    assert [p["t"] for p in result] == [1000, 2000, 3000]


def test_detect_gaps():
    base = _now_ms()
    points = [
        {"t": base, "sgv": 100},
        {"t": base + 5 * 60 * 1000, "sgv": 105},      # +5 min, no gap
        {"t": base + 20 * 60 * 1000, "sgv": 110},      # +15 min gap (>12)
        {"t": base + 25 * 60 * 1000, "sgv": 115},      # +5 min, no gap
    ]
    gaps = detect_gaps(points)
    assert len(gaps) == 1


def test_compute_metrics_empty():
    m = compute_metrics([])
    assert m["mean"] is None
    assert m["tir"] is None
    assert m["coverage_percent"] is None


def test_compute_metrics_basic():
    now = _now_ms()
    points = [
        {"t": now - 30 * 60 * 1000, "sgv": 100},
        {"t": now - 15 * 60 * 1000, "sgv": 120},
        {"t": now, "sgv": 150},
    ]
    m = compute_metrics(points)
    assert m["mean"] is not None
    assert m["last"] == 150
    assert m["tir"] is not None
    assert m["coverage_percent"] is not None
    assert m["delta_15m"] is not None


def test_resample_5min():
    base = 0
    points = [
        {"t": base, "sgv": 100},
        {"t": base + 60_000, "sgv": 110},        # same 5-min bucket
        {"t": base + 300_000, "sgv": 120},        # next bucket
    ]
    result = resample_5min(points)
    assert len(result) == 2
    assert result[0]["sgv"] == 105  # avg(100, 110)
    assert result[1]["sgv"] == 120
