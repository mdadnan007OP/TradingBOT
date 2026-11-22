"""News engine service: orchestrates providers, storage, and risk context.

The service is read-only with respect to trading: it never places, modifies or
closes orders. It collects economic-calendar events from configured providers,
stores/deduplicates them, and builds an optional ``NewsRiskContext`` that the
Phase 6 Risk Management Engine can consume to restrict new entries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from src.news.base import (
    CalendarProvider,
    NewsEngineABC,
    NewsProvider,
    NewsWindowStatus,
)
from src.news.config import NewsConfig
from src.news.models import EconomicEvent, NewsRiskContext
from src.news.persistence.repository import EventRepository
from src.news.filters.restriction import build_news_risk_context


@dataclass
class NewsService(NewsEngineABC):
    """Orchestrates economic-calendar providers into a risk context."""

    config: NewsConfig
    calendar_providers: List[CalendarProvider] = field(default_factory=list)
    news_providers: List[NewsProvider] = field(default_factory=list)
    repository: EventRepository = field(default_factory=EventRepository)

    def __post_init__(self) -> None:
        self._provider_index: Dict[str, CalendarProvider] = {}
        for p in self.calendar_providers:
            self._provider_index[p.provider_id] = p
        self._last_successful_update: Optional[datetime] = None

    # ---- Provider management -------------------------------------------

    def add_calendar_provider(self, provider: CalendarProvider) -> None:
        self.calendar_providers.append(provider)
        self._provider_index[provider.provider_id] = provider

    def add_news_provider(self, provider: NewsProvider) -> None:
        self.news_providers.append(provider)

    # ---- Collection -----------------------------------------------------

    def refresh(
        self,
        start: datetime,
        end: datetime,
        currencies: Optional[List[str]] = None,
        now: Optional[datetime] = None,
    ) -> Dict[str, int]:
        """Collect events from all selected calendar providers into the store."""
        now = now or datetime.now(timezone.utc)
        totals = {"collected": 0, "added": 0, "merged": 0, "duplicates": 0}
        selected = [
            self._provider_index[pid]
            for pid in self.config.provider_ids
            if pid in self._provider_index
        ]
        for provider in selected:
            events = provider.get_events(start, end, currencies)
            totals["collected"] += len(events)
            result = self.repository.ingest(events)
            totals["added"] += result["added"]
            totals["merged"] += result["merged"]
            totals["duplicates"] += result["duplicates"]
        if selected:
            self._last_successful_update = now
        return totals

    # ---- Queries --------------------------------------------------------

    def events_in_window(
        self,
        start: datetime,
        end: datetime,
        currencies: Optional[List[str]] = None,
    ) -> List[EconomicEvent]:
        """Return stored events with scheduled time in [start, end] (UTC)."""
        return self.repository.in_range(start, end, currencies)

    def events_for_instrument(
        self,
        instrument: str,
        start: datetime,
        end: datetime,
    ) -> List[EconomicEvent]:
        """Return stored events relevant to an instrument within [start, end]."""
        from src.news.filters.relevance import relevant_events_for_instrument

        return relevant_events_for_instrument(
            self.repository.in_range(start, end), instrument, self.config
        )

    def events_as_of(
        self,
        as_of: datetime,
        start: datetime,
        end: datetime,
        currencies: Optional[List[str]] = None,
    ) -> List[EconomicEvent]:
        """Leakage-safe query: only events whose information existed by ``as_of``.

        Excludes events whose ``retrieval_time`` is after ``as_of`` and events
        whose ``publication_time`` (actual value) is after ``as_of``. This
        prevents using future information in historical/backtest contexts.
        """
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        result: List[EconomicEvent] = []
        for event in self.repository.in_range(start, end, currencies):
            if event.retrieval_time is not None and event.retrieval_time > as_of:
                continue
            if event.publication_time is not None and event.publication_time > as_of:
                # The actual value was published in the future — not known yet.
                continue
            result.append(event)
        return result

    # ---- Freshness / staleness -----------------------------------------

    def last_update(self) -> Optional[datetime]:
        return self._last_successful_update

    def is_stale(self, now: Optional[datetime] = None) -> bool:
        """Return True if no successful refresh within stale_after_minutes."""
        if self._last_successful_update is None:
            return True
        now = now or datetime.now(timezone.utc)
        return (
            now - self._last_successful_update
            > timedelta(minutes=self.config.stale_after_minutes)
        )

    # ---- Risk context ---------------------------------------------------

    def risk_context(
        self,
        instrument: str,
        now: Optional[datetime] = None,
    ) -> NewsRiskContext:
        """Build a NewsRiskContext for an instrument from stored events.

        Considers events within a horizon of ``max window + stale`` around now so
        both imminent and recently-released events are included.
        """
        now = now or datetime.now(timezone.utc)
        if not self.config.enabled:
            return NewsRiskContext(
                instrument=instrument,
                window_status=NewsWindowStatus.NEWS_CLEAR,
                data_reliable=True,
                restriction_reason="News engine disabled",
                evaluated_at=now,
            )

        # Horizon: look ahead 24h and back far enough to cover post-windows.
        horizon = timedelta(hours=24)
        lookback = timedelta(
            minutes=max(
                (w.post_minutes for w in self.config.default_windows.values()),
                default=20,
            )
            + 60
        )
        candidates = self.repository.in_range(
            now - lookback, now + horizon
        )
        # Include unresolved-time events so EVENT_TIME_UNCERTAIN can be flagged.
        candidates = candidates + self.repository.unresolved()

        data_reliable = not self.is_stale(now)
        reason = None
        if not data_reliable:
            reason = (
                "No recent successful calendar refresh "
                f"(last update: {self._last_successful_update})"
            )

        return build_news_risk_context(
            candidates,
            instrument,
            self.config,
            now=now,
            data_reliable=data_reliable,
            unavailable_reason=reason,
        )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"NewsService(providers={list(self._provider_index)}, "
            f"events={len(self.repository)})"
        )