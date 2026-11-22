"""Tests for NewsService orchestration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.news.base import NewsWindowStatus
from src.news.config import test_news_config
from src.news.service import NewsService
from src.news.providers.mock_provider import MockCalendarProvider

BASE = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)


def _service():
    cfg = test_news_config()
    return NewsService(
        config=cfg,
        calendar_providers=[MockCalendarProvider(base_time=BASE)],
    )


def test_service_refresh_collects_events():
    svc = _service()
    counts = svc.refresh(BASE, BASE + timedelta(days=2))
    assert counts["collected"] > 0
    assert len(svc.repository) > 0


def test_service_last_update_and_fresh():
    svc = _service()
    svc.refresh(BASE, BASE + timedelta(days=2), now=BASE)
    assert svc.last_update() == BASE
    assert svc.is_stale(now=BASE) is False


def test_service_is_stale_when_no_refresh():
    svc = _service()
    assert svc.is_stale(now=BASE) is True


def test_service_is_stale_after_timeout():
    svc = _service()
    svc.refresh(BASE, BASE + timedelta(days=2), now=BASE)
    # stale_after_minutes=240 → 5 hours later is stale.
    assert svc.is_stale(now=BASE + timedelta(hours=5)) is True


def test_service_events_in_window():
    svc = _service()
    svc.refresh(BASE, BASE + timedelta(days=2))
    events = svc.events_in_window(BASE, BASE + timedelta(minutes=300))
    # CPI at +120, GDP UK at +90 within window
    assert len(events) >= 1


def test_service_risk_context_clear_when_far():
    svc = _service()
    svc.refresh(BASE, BASE + timedelta(days=2), now=BASE)
    # At BASE, nearest USD event (CPI) is +120 min → outside windows → clear.
    ctx = svc.risk_context("EURUSD", now=BASE)
    assert ctx.window_status == NewsWindowStatus.NEWS_CLEAR


def test_service_risk_context_blocks_near_high_impact():
    svc = _service()
    svc.refresh(BASE, BASE + timedelta(days=2), now=BASE)
    # CPI at +120 min. Evaluate 15 min before it → within pre-window → block.
    ctx = svc.risk_context("EURUSD", now=BASE + timedelta(minutes=105))
    assert ctx.window_status == NewsWindowStatus.BLOCK_NEW_ENTRIES
    assert ctx.blocks_new_entries is True


def test_service_risk_context_stale_blocks():
    svc = _service()
    svc.refresh(BASE, BASE + timedelta(days=2), now=BASE)
    # Evaluate 5 hours after last update → stale → NEWS_DATA_UNAVAILABLE.
    ctx = svc.risk_context("EURUSD", now=BASE + timedelta(hours=5))
    assert ctx.data_reliable is False
    assert ctx.blocks_new_entries is True


def test_service_risk_context_disabled_engine():
    cfg = test_news_config(overrides={"enabled": False})
    svc = NewsService(config=cfg, calendar_providers=[MockCalendarProvider(base_time=BASE)])
    svc.refresh(BASE, BASE + timedelta(days=2), now=BASE)
    ctx = svc.risk_context("EURUSD", now=BASE)
    assert ctx.window_status == NewsWindowStatus.NEWS_CLEAR
    assert "disabled" in (ctx.restriction_reason or "").lower()


def test_service_events_as_of_leakage_prevention():
    svc = _service()
    svc.refresh(BASE, BASE + timedelta(days=2), now=BASE)
    # as_of = BASE: events retrieved at BASE are known; nothing with future
    # publication_time should leak. All retrieval_time == BASE so all known.
    known = svc.events_as_of(BASE, BASE, BASE + timedelta(days=2))
    assert len(known) >= 1
    # as_of one minute BEFORE retrieval → nothing known.
    before = svc.events_as_of(BASE - timedelta(minutes=1), BASE, BASE + timedelta(days=2))
    assert before == []


def test_service_risk_context_unresolved_time_blocks():
    from tests.news.conftest import make_event
    from src.news.base import Importance
    svc = _service()
    svc.refresh(BASE, BASE + timedelta(days=2), now=BASE)
    # Inject an unresolved-time USD event.
    svc.repository.add(
        make_event(event_id="unres", currency="USD", name="CPI m/m",
                   importance=Importance.HIGH, scheduled_time=None,
                   time_resolved=False, minutes_offset=None)
    )
    ctx = svc.risk_context("EURUSD", now=BASE)
    assert ctx.window_status == NewsWindowStatus.EVENT_TIME_UNCERTAIN


def test_service_selected_providers_only():
    cfg = test_news_config()
    svc = NewsService(config=cfg, calendar_providers=[MockCalendarProvider(base_time=BASE)])
    # provider_ids default ["mock"]; provider registered as "mock".
    counts = svc.refresh(BASE, BASE + timedelta(days=2))
    assert counts["collected"] > 0