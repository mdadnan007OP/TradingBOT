"""Deterministic mock economic-calendar and news providers.

Generates reproducible simulated events (CPI, NFP, FOMC, rate decisions, etc.)
for automated testing. All events are clearly labelled as simulated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from src.news.base import (
    CalendarProvider,
    EventCategory,
    EventStatus,
    Importance,
    NewsProvider,
)
from src.news.models import EconomicEvent, NewsArticle


@dataclass
class MockCalendarProvider(CalendarProvider):
    """Deterministic simulated economic calendar provider."""

    base_time: datetime = field(
        default_factory=lambda: datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    )
    provider_id: str = "mock"
    is_simulated: bool = True

    def get_events(
        self,
        start: datetime,
        end: datetime,
        currencies: Optional[List[str]] = None,
    ) -> List[EconomicEvent]:
        """Return a fixed set of simulated events within [start, end]."""
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        currencies_upper = {c.upper() for c in currencies} if currencies else None
        events: List[EconomicEvent] = []
        for event in _simulated_events(self.base_time, self.provider_id):
            if currencies_upper is not None and event.currency.upper() not in currencies_upper:
                continue
            if start <= event.scheduled_time <= end:
                events.append(event)
        return events


def _simulated_events(base: datetime, provider_id: str) -> List[EconomicEvent]:
    """Build a deterministic set of simulated events anchored at ``base``."""
    def ev(
        eid, currency, country, name, importance, minutes_offset,
        actual=None, forecast=None, previous=None, category=EventCategory.OTHER,
    ) -> EconomicEvent:
        ts = base + timedelta(minutes=minutes_offset)
        return EconomicEvent(
            event_id=eid,
            provider_id=provider_id,
            country=country,
            currency=currency,
            event_name=name,
            category=category,
            importance=importance,
            raw_importance=importance.value,
            scheduled_time=ts,
            scheduled_time_original=ts,
            original_timezone="UTC",
            time_resolved=True,
            actual_value=actual,
            forecast_value=forecast,
            previous_value=previous,
            status=EventStatus.SCHEDULED,
            retrieval_time=base,
            last_update_time=base,
            source_provenance=f"simulated:{provider_id}",
            provider_freshness=base,
        )

    return [
        ev("mock-cpi-us", "USD", "US", "CPI m/m", Importance.HIGH, 120,
           actual="0.3%", forecast="0.2%", previous="0.1%", category=EventCategory.INFLATION),
        ev("mock-nfp-us", "USD", "US", "Nonfarm Payrolls", Importance.HIGH, 600,
           actual="180K", forecast="160K", previous="150K", category=EventCategory.EMPLOYMENT),
        ev("mock-fomc-us", "USD", "US", "FOMC Interest Rate Decision", Importance.HIGH, 1440,
           actual="5.25%", forecast="5.25%", previous="5.25%", category=EventCategory.CENTRAL_BANK),
        ev("mock-employment-eu", "EUR", "EU", "ECB Interest Rate Decision", Importance.HIGH, 300,
           actual="4.00%", forecast="4.00%", previous="4.00%", category=EventCategory.CENTRAL_BANK),
        ev("mock-gdp-uk", "GBP", "GB", "GDP m/m", Importance.MEDIUM, 90,
           actual="0.1%", forecast="0.2%", previous="0.0%", category=EventCategory.GROWTH),
        ev("mock-pmi-jp", "JPY", "JP", "Manufacturing PMI", Importance.MEDIUM, 45,
           actual="50.1", forecast="49.8", previous="49.5", category=EventCategory.GROWTH),
        ev("mock-retail-au", "AUD", "AU", "Retail Sales m/m", Importance.MEDIUM, 180,
           category=EventCategory.GROWTH),
        ev("mock-eia-oil", "USD", "US", "EIA Crude Oil Inventories", Importance.MEDIUM, 720,
           actual="-1.2M", forecast="-0.5M", previous="0.3M", category=EventCategory.COMMODITIES),
    ]


@dataclass
class MockNewsProvider(NewsProvider):
    """Deterministic simulated news provider."""

    base_time: datetime = field(
        default_factory=lambda: datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    )
    provider_id: str = "mock_news"
    is_simulated: bool = True

    def get_articles(
        self,
        start: datetime,
        end: datetime,
    ) -> List[NewsArticle]:
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return [
            NewsArticle(
                article_id="mock-art-1",
                source_name="Simulated News",
                headline="Central bank holds rates steady",
                url="https://example.com/mock/1",
                published_time=start,
                retrieval_time=start,
                related_currencies=["USD", "EUR"],
                duplicate_key="mock-art-1",
            )
        ]