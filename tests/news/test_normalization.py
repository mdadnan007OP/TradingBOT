"""Tests for event normalization."""

from __future__ import annotations

from datetime import datetime, timezone

from src.news.base import EventCategory, Importance
from src.news.normalization import normalize_event, normalize_importance


def test_normalize_importance_from_string():
    assert normalize_importance("high") == Importance.HIGH
    assert normalize_importance("MEDIUM") == Importance.MEDIUM
    assert normalize_importance("low") == Importance.LOW
    assert normalize_importance("unknown") == Importance.UNKNOWN
    assert normalize_importance(None) == Importance.UNKNOWN


def test_normalize_importance_from_number():
    assert normalize_importance(3) == Importance.HIGH
    assert normalize_importance(2) == Importance.MEDIUM
    assert normalize_importance(1) == Importance.LOW
    assert normalize_importance(0) == Importance.UNKNOWN


def test_normalize_event_maps_fields():
    raw = {
        "event_id": "us-cpi",
        "country": "US",
        "currency": "usd",
        "event_name": "CPI m/m",
        "importance": "high",
        "scheduled_time": datetime(2026, 1, 1, 13, 30, tzinfo=timezone.utc),
        "actual": "0.3%",
        "forecast": "0.2%",
        "previous": "0.1%",
    }
    ev = normalize_event(raw, "test_provider")
    assert ev.event_id == "us-cpi"
    assert ev.currency == "USD"
    assert ev.importance == Importance.HIGH
    assert ev.category == EventCategory.INFLATION
    assert ev.actual_value == "0.3%"
    assert ev.forecast_value == "0.2%"
    assert ev.previous_value == "0.1%"
    assert ev.time_resolved is True


def test_normalize_event_missing_values_stay_none():
    raw = {"currency": "USD", "event_name": "Retail Sales m/m"}
    ev = normalize_event(raw, "p")
    assert ev.actual_value is None
    assert ev.forecast_value is None
    assert ev.previous_value is None
    # No scheduled time provided → unresolved
    assert ev.scheduled_time is None
    assert ev.time_resolved is False


def test_normalize_event_category_classification():
    raw = {"currency": "USD", "event_name": "Nonfarm Payrolls"}
    ev = normalize_event(raw, "p")
    assert ev.category == EventCategory.EMPLOYMENT


def test_normalize_event_event_id_fallback():
    raw = {"currency": "USD", "event_name": "GDP m/m"}
    ev = normalize_event(raw, "prov")
    assert ev.event_id.startswith("prov:")
    assert "gdp" in ev.event_id.lower()