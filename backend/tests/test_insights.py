"""Tests for insights module."""

from datetime import datetime, timezone

from app.insights import compute_dayparts, compute_hypo_heatmap


def _ts(year: int, month: int, day: int, hour: int, minute: int = 0) -> int:
    """Helper to create ms timestamp."""
    dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def test_hypo_heatmap_empty():
    result = compute_hypo_heatmap([])
    assert result["days"] == []
    assert result["values"] == []


def test_hypo_heatmap_counts():
    # Two hypo readings on same day at hour 3 (5-min grid => 5 min each)
    points = [
        {"t": _ts(2025, 1, 10, 3, 0), "sgv": 65},
        {"t": _ts(2025, 1, 10, 3, 5), "sgv": 60},
        {"t": _ts(2025, 1, 10, 14, 0), "sgv": 120},  # not hypo
    ]
    result = compute_hypo_heatmap(points)
    assert len(result["days"]) == 1
    assert result["days"][0] == "2025-01-10"
    # hour 3 should have 2 readings * 5 min = 10 minutes
    assert result["values"][0][3] == 10


def test_dayparts_structure():
    points = [
        {"t": _ts(2025, 1, 10, 2, 0), "sgv": 100},   # Night (Mon)
        {"t": _ts(2025, 1, 10, 8, 0), "sgv": 150},   # Morning
        {"t": _ts(2025, 1, 10, 14, 0), "sgv": 200},  # Afternoon
        {"t": _ts(2025, 1, 10, 20, 0), "sgv": 120},  # Evening
        {"t": _ts(2025, 1, 11, 2, 0), "sgv": 90},    # Night (Sat)
        {"t": _ts(2025, 1, 11, 8, 0), "sgv": 130},   # Morning (Sat)
    ]
    result = compute_dayparts(points)
    assert "definition" in result
    assert len(result["definition"]) == 4
    assert len(result["overall"]) == 4
    assert len(result["weekday"]) == 4
    assert len(result["weekend"]) == 4

    # Night overall should have data
    night = result["overall"][0]
    assert night["name"] == "Night"
    assert night["tir"] is not None
