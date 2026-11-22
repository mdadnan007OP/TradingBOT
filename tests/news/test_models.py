"""Tests for news models and enums."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.news.base import EventCategory, Importance, NewsWindowStatus
from src.news.models import EconomicEvent, NewsRiskContext
from tests.news.conftest import make_event


def test_economic_event_utc_normalization():
    naive = datetime(2026, 1, 1, 12, 0)
    ev = make_event(scheduled_time=naive, time_resolved=True)
    assert ev.scheduled_time.tzinfo is not None
    assert ev.scheduled_time.utcoffset() == timedelta(0)


def test_economic_event_offsets_converted_to_utc():
    tz = timezone(timedelta(hours=2))
    local = datetime(2026, 1, 1, 12, 0, tzinfo=tz)
    ev = make_event(scheduled_time=local, time_resolved=True)
    assert ev.scheduled_time == datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)


def test_economic_event_is_simulated():
    ev = make_event(source="simulated:mock")
    assert ev.is_simulated is True
    ev2 = make_event(source="mt5_calendar")
    assert ev2.is_simulated is False


def test_economic_event_is_relevant_to():
    ev = make_event(currency="EUR")
    assert ev.is_relevant_to("EUR") is True
    assert ev.is_relevant_to("eur") is True
    assert ev.is_relevant_to("USD") is False


def test_economic_event_missing_values_not_invented():
    ev = EconomicEvent(
        event_id="x", provider_id="p", country="US", currency="USD",
        event_name="Retail Sales", category=EventCategory.GROWTH,
        importance=Importance.MEDIUM,
    )
    assert ev.actual_value is None
    assert ev.forecast_value is None
    assert ev.previous_value is None
    assert ev.scheduled_time is None


def test_news_risk_context_blocks_new_entries():
    ctx = NewsRiskContext(
        instrument="EURUSD",
        window_status=NewsWindowStatus.BLOCK_NEW_ENTRIES,
    )
    assert ctx.blocks_new_entries is True

    ctx2 = NewsRiskContext(
        instrument="EURUSD",
        window_status=NewsWindowStatus.EVENT_TIME_UNCERTAIN,
    )
    assert ctx2.blocks_new_entries is True

    ctx3 = NewsRiskContext(
        instrument="EURUSD",
        window_status=NewsWindowStatus.NEWS_DATA_UNAVAILABLE,
    )
    assert ctx3.blocks_new_entries is True

    ctx4 = NewsRiskContext(
        instrument="EURUSD",
        window_status=NewsWindowStatus.NEWS_CAUTION,
    )
    assert ctx4.blocks_new_entries is False
    assert ctx4.is_caution is True


def test_news_risk_context_to_dict():
    ctx = NewsRiskContext(
        instrument="EURUSD",
        max_importance=Importance.HIGH,
        window_status=NewsWindowStatus.BLOCK_NEW_ENTRIES,
        time_until_event=timedelta(minutes=5),
        evaluated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    d = ctx.to_dict()
    assert d["instrument"] == "EURUSD"
    assert d["max_importance"] == "HIGH"
    assert d["window_status"] == "BLOCK_NEW_ENTRIES"
    assert d["time_until_event_seconds"] == 300.0
    assert d["evaluated_at"] is not None