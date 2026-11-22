"""Phase 7 news engine tests — shared fixtures."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.news.base import EventCategory, Importance, EventStatus
from src.news.config import NewsConfig, test_news_config
from src.news.models import EconomicEvent

BASE = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def config():
    return test_news_config()


@pytest.fixture
def base_time():
    return BASE


def make_event(
    event_id="evt-1",
    currency="USD",
    country="US",
    name="CPI m/m",
    importance=Importance.HIGH,
    minutes_offset=0,
    category=EventCategory.INFLATION,
    scheduled_time=None,
    time_resolved=True,
    actual="0.3%",
    forecast="0.2%",
    previous="0.1%",
    provider_id="test",
    base=BASE,
    source="test-provider",
):
    if scheduled_time is None and minutes_offset is not None:
        scheduled_time = base + timedelta(minutes=minutes_offset)
    return EconomicEvent(
        event_id=event_id,
        provider_id=provider_id,
        country=country,
        currency=currency,
        event_name=name,
        category=category,
        importance=importance,
        raw_importance=importance.value,
        scheduled_time=scheduled_time,
        scheduled_time_original=scheduled_time,
        original_timezone="UTC",
        time_resolved=time_resolved,
        actual_value=actual,
        forecast_value=forecast,
        previous_value=previous,
        status=EventStatus.SCHEDULED,
        retrieval_time=base,
        last_update_time=base,
        source_provenance=source,
        provider_freshness=base,
    )


@pytest.fixture
def event_factory():
    return make_event