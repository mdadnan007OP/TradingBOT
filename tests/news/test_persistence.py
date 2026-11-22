"""Tests for persistence: repository and history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.news.base import EventStatus
from src.news.persistence.repository import EventRepository
from src.news.persistence.event_history import EventHistory
from tests.news.conftest import make_event

BASE = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)


def test_repository_add_and_get():
    repo = EventRepository()
    e = make_event(event_id="a")
    repo.add(e)
    assert repo.get("a") is e
    assert len(repo) == 1


def test_repository_ingest_dedup():
    repo = EventRepository()
    events = [
        make_event(event_id="a", currency="USD", name="CPI", minutes_offset=120),
        make_event(event_id="a", currency="USD", name="CPI", minutes_offset=120),
        make_event(event_id="b", currency="EUR", name="ECB", minutes_offset=300),
    ]
    counts = repo.ingest(events)
    assert counts["duplicates"] == 1
    assert counts["added"] == 2
    assert len(repo) == 2


def test_repository_in_range():
    repo = EventRepository()
    repo.add(make_event(event_id="a", currency="USD", name="CPI", minutes_offset=120))
    repo.add(make_event(event_id="b", currency="EUR", name="ECB", minutes_offset=600))
    result = repo.in_range(BASE, BASE + timedelta(minutes=300))
    ids = {e.event_id for e in result}
    assert ids == {"a"}


def test_repository_in_range_currency_filter():
    repo = EventRepository()
    repo.add(make_event(event_id="a", currency="USD", name="CPI", minutes_offset=120))
    repo.add(make_event(event_id="b", currency="EUR", name="ECB", minutes_offset=300))
    result = repo.in_range(BASE, BASE + timedelta(days=1), currencies=["EUR"])
    assert [e.event_id for e in result] == ["b"]


def test_repository_unresolved():
    repo = EventRepository()
    repo.add(make_event(event_id="u", currency="USD", name="CPI",
                        scheduled_time=None, time_resolved=False, minutes_offset=None))
    repo.add(make_event(event_id="a", currency="USD", name="CPI", minutes_offset=120))
    assert [e.event_id for e in repo.unresolved()] == ["u"]


def test_repository_merge_revision_via_add():
    repo = EventRepository()
    repo.add(make_event(event_id="a", currency="USD", name="CPI",
                        minutes_offset=120, actual="0.2%"))
    repo.add(make_event(event_id="a", currency="USD", name="CPI",
                        minutes_offset=120, actual="0.3%"))
    ev = repo.get("a")
    assert ev.actual_value == "0.3%"
    assert ev.status == EventStatus.REVISED


def test_event_history_timeline():
    hist = EventHistory()
    e1 = make_event(event_id="a", actual="0.2%")
    e2 = make_event(event_id="a", actual="0.3%")
    hist.record(e1)
    hist.record(e2)
    assert len(hist.timeline("a")) == 2
    assert hist.revision_count("a") == 1
    assert hist.latest("a").actual_value == "0.3%"


def test_repository_history_reflects_revisions():
    repo = EventRepository()
    repo.add(make_event(event_id="a", actual="0.2%"))
    repo.add(make_event(event_id="a", actual="0.3%"))
    assert len(repo.history("a")) == 2
    assert repo.history("a")[0].actual_value == "0.2%"