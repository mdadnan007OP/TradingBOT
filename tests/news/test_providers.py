"""Tests for economic-calendar providers."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from src.news.base import Importance
from src.news.providers.mock_provider import MockCalendarProvider
from src.news.providers.csv_provider import CsvCalendarProvider
from src.news.providers.mt5_calendar_provider import MT5CalendarProvider

BASE = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)


def test_mock_provider_deterministic():
    p1 = MockCalendarProvider(base_time=BASE)
    p2 = MockCalendarProvider(base_time=BASE)
    start, end = BASE, BASE + timedelta(days=2)
    a = p1.get_events(start, end)
    b = p2.get_events(start, end)
    assert [e.event_id for e in a] == [e.event_id for e in b]
    assert len(a) > 0


def test_mock_provider_contains_cpi_nfp_fomc():
    p = MockCalendarProvider(base_time=BASE)
    events = p.get_events(BASE, BASE + timedelta(days=2))
    names = " ".join(e.event_name for e in events).lower()
    assert "cpi" in names
    assert "nonfarm" in names
    assert "fomc" in names


def test_mock_provider_currency_filter():
    p = MockCalendarProvider(base_time=BASE)
    events = p.get_events(BASE, BASE + timedelta(days=2), currencies=["USD"])
    assert all(e.currency == "USD" for e in events)
    assert len(events) > 0


def test_mock_provider_time_window():
    p = MockCalendarProvider(base_time=BASE)
    # Window that excludes everything.
    events = p.get_events(BASE + timedelta(days=100), BASE + timedelta(days=101))
    assert events == []


def test_mock_provider_events_labeled_simulated():
    p = MockCalendarProvider(base_time=BASE)
    events = p.get_events(BASE, BASE + timedelta(days=2))
    assert all(e.is_simulated for e in events)


def test_csv_provider(tmp_path):
    csv_file = tmp_path / "cal.csv"
    csv_file.write_text(
        "event_id,currency,event_name,importance,scheduled_time,actual,forecast,previous\n"
        "e1,USD,CPI m/m,high,2026-01-01T13:30:00+00:00,0.3%,0.2%,0.1%\n"
        "e2,EUR,ECB Rate Decision,high,2026-01-01T14:15:00+00:00,4.0%,4.0%,4.0%\n",
        encoding="utf-8",
    )
    p = CsvCalendarProvider(path=str(csv_file))
    events = p.get_events(BASE, BASE + timedelta(days=1))
    assert len(events) == 2
    assert events[0].currency == "USD"
    assert events[0].actual_value == "0.3%"
    assert events[0].importance == Importance.HIGH


def test_csv_provider_missing_columns_raises(tmp_path):
    csv_file = tmp_path / "bad.csv"
    csv_file.write_text("currency,importance\nUSD,high\n", encoding="utf-8")
    p = CsvCalendarProvider(path=str(csv_file))
    import pytest
    with pytest.raises(ValueError, match="missing required columns"):
        p.get_events(BASE, BASE + timedelta(days=1))


def test_csv_provider_currency_filter(tmp_path):
    csv_file = tmp_path / "cal.csv"
    csv_file.write_text(
        "event_id,currency,event_name,importance,scheduled_time\n"
        "e1,USD,CPI m/m,high,2026-01-01T13:30:00+00:00\n"
        "e2,EUR,ECB Rate Decision,high,2026-01-01T14:15:00+00:00\n",
        encoding="utf-8",
    )
    p = CsvCalendarProvider(path=str(csv_file))
    events = p.get_events(BASE, BASE + timedelta(days=1), currencies=["EUR"])
    assert len(events) == 1
    assert events[0].currency == "EUR"


def test_mt5_provider_resolves_server_tz(tmp_path):
    f = tmp_path / "mt5.json"
    # Server time 14:30 Berlin (CET, UTC+1 in January) → 13:30 UTC.
    f.write_text(
        json.dumps([
            {
                "event_id": "m1", "country": "DE", "currency": "EUR",
                "event_name": "ECB Rate Decision", "importance": "high",
                "server_time": "2026-01-01T14:30:00",
                "actual": "4.0%", "forecast": "4.0%", "previous": "4.0%",
            }
        ]),
        encoding="utf-8",
    )
    p = MT5CalendarProvider(path=str(f), server_timezone="Europe/Berlin")
    events = p.get_events(BASE, BASE + timedelta(days=1))
    assert len(events) == 1
    ev = events[0]
    assert ev.time_resolved is True
    assert ev.scheduled_time == datetime(2026, 1, 1, 13, 30, tzinfo=timezone.utc)
    assert ev.actual_value == "4.0%"


def test_mt5_provider_unresolved_when_tz_unknown(tmp_path):
    f = tmp_path / "mt5.json"
    f.write_text(
        json.dumps([
            {"event_id": "m1", "currency": "USD", "event_name": "CPI m/m",
             "importance": "high", "server_time": "2026-01-01T14:30:00"}
        ]),
        encoding="utf-8",
    )
    p = MT5CalendarProvider(path=str(f))  # no server_timezone
    events = p.get_events(BASE, BASE + timedelta(days=1))
    assert len(events) == 1
    ev = events[0]
    assert ev.time_resolved is False
    assert ev.scheduled_time is None


def test_mt5_provider_dst_handling(tmp_path):
    f = tmp_path / "mt5.json"
    # July: Berlin is CEST (UTC+2). 14:30 local → 12:30 UTC.
    f.write_text(
        json.dumps([
            {"event_id": "m1", "currency": "EUR", "event_name": "PMI",
             "importance": "medium", "server_time": "2026-07-01T14:30:00"}
        ]),
        encoding="utf-8",
    )
    p = MT5CalendarProvider(path=str(f), server_timezone="Europe/Berlin")
    events = p.get_events(
        datetime(2026, 7, 1, tzinfo=timezone.utc),
        datetime(2026, 7, 2, tzinfo=timezone.utc),
    )
    assert len(events) == 1
    assert events[0].scheduled_time == datetime(2026, 7, 1, 12, 30, tzinfo=timezone.utc)


def test_mt5_provider_csv(tmp_path):
    f = tmp_path / "mt5.csv"
    f.write_text(
        "event_id,currency,event_name,importance,server_time\n"
        "m1,USD,CPI m/m,high,2026-01-01T14:30:00\n",
        encoding="utf-8",
    )
    p = MT5CalendarProvider(path=str(f), server_timezone="Europe/Berlin")
    events = p.get_events(BASE, BASE + timedelta(days=1))
    assert len(events) == 1
    assert events[0].time_resolved is True
    assert events[0].scheduled_time == datetime(2026, 1, 1, 13, 30, tzinfo=timezone.utc)