"""Event repository: dedup, revision merging, and time-range queries.

In-memory store used by the news service and available for future persistence
backends (files/database). Never fabricates missing values.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.news.calendar.revisions import (
    deduplicate_events,
    merge_revision,
)
from src.news.models import EconomicEvent
from src.news.persistence.event_history import EventHistory


class EventRepository:
    """Holds economic events keyed by event_id with dedup + revision support."""

    def __init__(self, history: Optional[EventHistory] = None) -> None:
        self._events: Dict[str, EconomicEvent] = {}
        self._history = history or EventHistory()

    def add(self, event: EconomicEvent) -> None:
        """Add or merge an event. Existing events are merged (revised)."""
        existing = self._events.get(event.event_id)
        if existing is None:
            self._events[event.event_id] = event
            self._history.record(event)
            return
        merged = merge_revision(existing, event)
        if merged != existing:
            self._events[event.event_id] = merged
            self._history.record(merged)

    def add_many(self, events: List[EconomicEvent]) -> None:
        for e in events:
            self.add(e)

    def ingest(self, events: List[EconomicEvent]) -> Dict[str, int]:
        """Ingest a batch with dedup; returns counts of added/merged/duplicates."""
        unique, duplicates = deduplicate_events(events)
        added = 0
        merged = 0
        for event in unique:
            existed = event.event_id in self._events
            self.add(event)
            if existed:
                merged += 1
            else:
                added += 1
        return {
            "added": added,
            "merged": merged,
            "duplicates": len(duplicates),
        }

    def get(self, event_id: str) -> Optional[EconomicEvent]:
        return self._events.get(event_id)

    def all(self) -> List[EconomicEvent]:
        return list(self._events.values())

    def in_range(
        self,
        start: datetime,
        end: datetime,
        currencies: Optional[List[str]] = None,
    ) -> List[EconomicEvent]:
        """Return events with scheduled time in [start, end] (UTC).

        Events with unresolved scheduled time are excluded from range queries
        (they cannot be placed in time) — callers should query `unresolved()`
        separately to flag EVENT_TIME_UNCERTAIN.
        """
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        currencies_upper = {c.upper() for c in currencies} if currencies else None
        result: List[EconomicEvent] = []
        for event in self._events.values():
            if currencies_upper is not None and event.currency.upper() not in currencies_upper:
                continue
            if event.scheduled_time is None:
                continue
            if start <= event.scheduled_time <= end:
                result.append(event)
        return result

    def unresolved(self) -> List[EconomicEvent]:
        """Return events whose scheduled time could not be resolved."""
        return [e for e in self._events.values() if e.scheduled_time is None]

    def history(self, event_id: str) -> List[EconomicEvent]:
        return self._history.timeline(event_id)

    def __len__(self) -> int:
        return len(self._events)