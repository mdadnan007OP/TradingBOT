"""Tests for filters: relevance, news windows, restriction builder."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.news.base import (
    EventCategory,
    Importance,
    NewsWindowStatus,
    UnavailablePolicy,
)
from src.news.config import ImpactWindow, test_news_config
from src.news.filters.relevance import (
    filter_relevant_events,
    relevant_events_for_instrument,
)
from src.news.filters.news_window import (
    compute_news_window_status,
    consolidate_windows,
)
from src.news.filters.restriction import build_news_risk_context
from tests.news.conftest import make_event

BASE = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)


def test_filter_relevant_events():
    cfg = test_news_config()
    events = [
        make_event(event_id="usd", currency="USD", name="CPI m/m"),
        make_event(event_id="eur", currency="EUR", name="ECB", importance=Importance.MEDIUM),
    ]
    rel = relevant_events_for_instrument(events, "EURUSD", cfg)
    assert len(rel) == 2
    rel_jpy = relevant_events_for_instrument(events, "USDJPY", cfg)
    assert [e.event_id for e in rel_jpy] == ["usd"]


def test_filter_min_importance():
    cfg = test_news_config()
    events = [
        make_event(event_id="high", currency="USD", name="CPI m/m", importance=Importance.HIGH),
        make_event(event_id="low", currency="USD", name="Minor", importance=Importance.LOW),
    ]
    assessments = filter_relevant_events(events, "EURUSD", cfg, min_importance=Importance.MEDIUM)
    ids = {a.event.event_id for a in assessments}
    assert "high" in ids
    assert "low" not in ids


def test_news_window_high_blocks():
    cfg = test_news_config()
    # CPI 30 min ahead → within high pre-window (30) → BLOCK.
    cpi = make_event(event_id="cpi", currency="USD", name="CPI m/m",
                     importance=Importance.HIGH, minutes_offset=30)
    assessments = filter_relevant_events([cpi], "EURUSD", cfg)
    status, reason = compute_news_window_status(assessments, cfg, now=BASE)
    assert status == NewsWindowStatus.BLOCK_NEW_ENTRIES
    assert reason is not None


def test_news_window_medium_blocks():
    cfg = test_news_config()
    # MEDIUM default window pre=15, post=10. Event 10 min ahead → within → BLOCK.
    ev = make_event(event_id="gdp", currency="USD", name="GDP m/m",
                    importance=Importance.MEDIUM, minutes_offset=10)
    assessments = filter_relevant_events([ev], "EURUSD", cfg)
    status, _ = compute_news_window_status(assessments, cfg, now=BASE)
    assert status == NewsWindowStatus.BLOCK_NEW_ENTRIES


def test_news_window_low_caution_only():
    cfg = test_news_config()
    # LOW default window pre=0 post=0; but caution_importance=MEDIUM so LOW
    # events don't even reach caution. Move a MEDIUM event far outside window.
    ev = make_event(event_id="far", currency="USD", name="GDP m/m",
                    importance=Importance.MEDIUM, minutes_offset=300)
    assessments = filter_relevant_events([ev], "EURUSD", cfg)
    status, _ = compute_news_window_status(assessments, cfg, now=BASE)
    assert status == NewsWindowStatus.NEWS_CLEAR


def test_news_window_outside_clear():
    cfg = test_news_config()
    cpi = make_event(event_id="cpi", currency="USD", name="CPI m/m",
                     importance=Importance.HIGH, minutes_offset=300)
    assessments = filter_relevant_events([cpi], "EURUSD", cfg)
    status, _ = compute_news_window_status(assessments, cfg, now=BASE)
    assert status == NewsWindowStatus.NEWS_CLEAR


def test_news_window_unresolved_time():
    cfg = test_news_config()
    ev = make_event(event_id="u", currency="USD", name="CPI m/m",
                    importance=Importance.HIGH, scheduled_time=None,
                    time_resolved=False, minutes_offset=None)
    assessments = filter_relevant_events([ev], "EURUSD", cfg)
    status, reason = compute_news_window_status(assessments, cfg, now=BASE)
    assert status == NewsWindowStatus.EVENT_TIME_UNCERTAIN
    assert reason is not None


def test_news_window_overlapping_events_block():
    cfg = test_news_config()
    # Two events, one far (clear) and one near (block). Consolidated → BLOCK.
    near = make_event(event_id="near", currency="USD", name="NFP",
                      importance=Importance.HIGH, minutes_offset=20)
    far = make_event(event_id="far", currency="USD", name="GDP",
                     importance=Importance.MEDIUM, minutes_offset=300)
    assessments = filter_relevant_events([near, far], "EURUSD", cfg)
    status, _ = compute_news_window_status(assessments, cfg, now=BASE)
    assert status == NewsWindowStatus.BLOCK_NEW_ENTRIES


def test_consolidate_windows_precedence():
    assert consolidate_windows([
        NewsWindowStatus.NEWS_CLEAR, NewsWindowStatus.BLOCK_NEW_ENTRIES
    ]) == NewsWindowStatus.BLOCK_NEW_ENTRIES
    assert consolidate_windows([
        NewsWindowStatus.NEWS_CAUTION, NewsWindowStatus.NEWS_CLEAR
    ]) == NewsWindowStatus.NEWS_CAUTION
    assert consolidate_windows([
        NewsWindowStatus.BLOCK_NEW_ENTRIES, NewsWindowStatus.EVENT_TIME_UNCERTAIN
    ]) == NewsWindowStatus.EVENT_TIME_UNCERTAIN


def test_build_news_risk_context_clear():
    cfg = test_news_config()
    far = make_event(event_id="far", currency="USD", name="GDP",
                     importance=Importance.MEDIUM, minutes_offset=600)
    ctx = build_news_risk_context([far], "EURUSD", cfg, now=BASE)
    assert ctx.window_status == NewsWindowStatus.NEWS_CLEAR
    assert ctx.blocks_new_entries is False
    assert ctx.data_reliable is True


def test_build_news_risk_context_blocking():
    cfg = test_news_config()
    cpi = make_event(event_id="cpi", currency="USD", name="CPI m/m",
                     importance=Importance.HIGH, minutes_offset=20)
    ctx = build_news_risk_context([cpi], "EURUSD", cfg, now=BASE)
    assert ctx.window_status == NewsWindowStatus.BLOCK_NEW_ENTRIES
    assert ctx.blocks_new_entries is True
    assert "cpi" in [e.lower() for e in ctx.relevant_event_ids] or ctx.relevant_event_ids


def test_build_news_risk_context_unavailable_blocks():
    cfg = test_news_config()
    ctx = build_news_risk_context(
        [], "EURUSD", cfg, now=BASE,
        data_reliable=False, unavailable_reason="stale",
    )
    assert ctx.window_status == NewsWindowStatus.NEWS_DATA_UNAVAILABLE
    assert ctx.data_reliable is False
    assert ctx.blocks_new_entries is True


def test_build_news_risk_context_unavailable_allow_warning():
    cfg = test_news_config(
        overrides={"unavailable_policy": UnavailablePolicy.ALLOW_WITH_WARNING}
    )
    ctx = build_news_risk_context(
        [], "EURUSD", cfg, now=BASE,
        data_reliable=False, unavailable_reason="stale",
    )
    assert ctx.data_reliable is False
    assert ctx.is_caution is True


def test_build_news_risk_context_max_importance_and_categories():
    cfg = test_news_config()
    events = [
        make_event(event_id="a", currency="USD", name="CPI m/m",
                   importance=Importance.HIGH, minutes_offset=600,
                   category=EventCategory.INFLATION),
        make_event(event_id="b", currency="USD", name="NFP",
                   importance=Importance.MEDIUM, minutes_offset=700,
                   category=EventCategory.EMPLOYMENT),
    ]
    ctx = build_news_risk_context(events, "EURUSD", cfg, now=BASE)
    assert ctx.max_importance == Importance.HIGH
    assert EventCategory.INFLATION in ctx.categories
    assert EventCategory.EMPLOYMENT in ctx.categories