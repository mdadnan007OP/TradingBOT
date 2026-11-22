"""Tests for calendar mapping, impact, scheduler, revisions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.news.base import EventCategory, Importance
from src.news.calendar.event_mapping import (
    currencies_for_instrument,
    instrument_is_relevant,
)
from src.news.calendar.impact import assess_impact
from src.news.calendar.scheduler import find_relevant_events, next_event_for_instrument
from src.news.calendar.revisions import deduplicate_events, merge_revision
from tests.news.conftest import make_event

BASE = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)


def test_currencies_for_instrument():
    from src.news.config import test_news_config
    cfg = test_news_config()
    assert set(currencies_for_instrument("EURUSD", cfg)) == {"EUR", "USD"}
    assert currencies_for_instrument("XAUUSD", cfg) == ["USD"]


def test_instrument_is_relevant():
    from src.news.config import test_news_config
    cfg = test_news_config()
    usd_cpi = make_event(currency="USD", name="CPI m/m")
    eur_event = make_event(event_id="e2", currency="EUR", name="ECB Rate")
    assert instrument_is_relevant("EURUSD", usd_cpi, cfg) is True
    assert instrument_is_relevant("EURUSD", eur_event, cfg) is True
    assert instrument_is_relevant("USDJPY", eur_event, cfg) is False


def test_instrument_is_relevant_energy_inventories():
    from src.news.config import test_news_config
    cfg = test_news_config()
    oil = make_event(currency="USD", name="EIA Crude Oil Inventories",
                     category=EventCategory.COMMODITIES)
    assert instrument_is_relevant("WTIUSD", oil, cfg) is True
    # EUR event not relevant to WTIUSD
    eur = make_event(event_id="e", currency="EUR", name="ECB")
    assert instrument_is_relevant("WTIUSD", eur, cfg) is False


def test_assess_impact_relevance_and_timing():
    from src.news.config import test_news_config
    cfg = test_news_config()
    cpi = make_event(currency="USD", name="CPI m/m", minutes_offset=120)
    a = assess_impact(cpi, "EURUSD", cfg, now=BASE)
    assert a.relevant is True
    assert a.time_until == timedelta(minutes=120)
    assert a.time_since is None


def test_assess_impact_not_relevant():
    from src.news.config import test_news_config
    cfg = test_news_config()
    eur = make_event(event_id="e", currency="EUR", name="ECB", minutes_offset=30)
    a = assess_impact(eur, "USDJPY", cfg, now=BASE)
    assert a.relevant is False


def test_find_relevant_events_in_horizon():
    from src.news.config import test_news_config
    cfg = test_news_config()
    events = [
        make_event(event_id="cpi", currency="USD", name="CPI m/m", minutes_offset=120),
        make_event(event_id="far", currency="USD", name="Something", minutes_offset=2000),
    ]
    results = find_relevant_events(events, "EURUSD", cfg, now=BASE, horizon=timedelta(hours=24))
    ids = {a.event.event_id for a in results}
    assert "cpi" in ids
    assert "far" not in ids


def test_next_event_for_instrument():
    from src.news.config import test_news_config
    cfg = test_news_config()
    events = [
        make_event(event_id="near", currency="USD", name="CPI", minutes_offset=30),
        make_event(event_id="far", currency="USD", name="NFP", minutes_offset=600),
    ]
    nxt = next_event_for_instrument(events, "EURUSD", cfg, now=BASE)
    assert nxt.event.event_id == "near"


def test_deduplicate_events():
    e1 = make_event(event_id="a", currency="USD", name="CPI", minutes_offset=120)
    e2 = make_event(event_id="a", currency="USD", name="CPI", minutes_offset=120)
    unique, dups = deduplicate_events([e1, e2])
    assert len(unique) == 1
    assert len(dups) == 1


def test_merge_revision_updates_actual():
    existing = make_event(event_id="a", currency="USD", name="CPI",
                          minutes_offset=120, actual="0.2%")
    new = make_event(event_id="a", currency="USD", name="CPI",
                     minutes_offset=120, actual="0.3%", forecast="0.25%")
    merged = merge_revision(existing, new)
    assert merged.actual_value == "0.3%"
    assert merged.forecast_value == "0.25%"
    from src.news.base import EventStatus
    assert merged.status == EventStatus.REVISED


def test_merge_revision_keeps_existing_when_new_missing():
    existing = make_event(event_id="a", currency="USD", name="CPI",
                          minutes_offset=120, actual="0.3%", forecast="0.2%")
    new = make_event(event_id="a", currency="USD", name="CPI",
                     minutes_offset=120, actual=None, forecast=None)
    merged = merge_revision(existing, new)
    assert merged.actual_value == "0.3%"
    assert merged.forecast_value == "0.2%"