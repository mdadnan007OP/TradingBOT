"""In-memory economic event store with filtering and time-range queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from src.news.models import EconomicEvent


@dataclass
class EconomicEventStore:
    """Holds events keyed by event_id; supports dedup and range queries."""

    _events: Dict[str, EconomicEvent] = field(default_factory=dict)

    def add(self, event: EconomicEvent) -> None:
        self._events[event.event_id] = event

    def add_many(self, events: List[EconomicEvent]) -> None:
        for e in events:
            self.add(e)

    def all(self) -> List[EconomicEvent]:
        return list(self._events.values())

    def get(self, event_id: str) -> Optional[EconomicEvent]:
        return self._events.get(event_id)

    def in_range(
        self,
        start: datetime,
        end: datetime,
        currencies: Optional[List[str]] = None,
    ) -> List[EconomicEvent]:
        """Return events whose scheduled time is within [start, end] (UTC).

        Events with unresolved scheduled time are included only when a currency
        filter is not provided (so callers can flag them).
        """
        currencies_upper = {c.upper() for c in currencies} if currencies else None
        result: List[EconomicEvent] = []
        for event in self._events.values():
            if currencies_upper is not None and event.currency.upper() not in currencies_upper:
                continue
            if event.scheduled_time is None:
                if currencies_upper is None:
                    result.append(event)
                continue
            if start <= event.scheduled_time <= end:
                result.append(event)
        return result

    def __len__(self) -> int:
        return len(self._events)