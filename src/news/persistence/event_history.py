"""Event history: tracks the revision/publication timeline of an event."""

from __future__ import annotations

from typing import Dict, List

from src.news.models import EconomicEvent


class EventHistory:
    """Records ordered snapshots of an event across revisions."""

    def __init__(self) -> None:
        self._timeline: Dict[str, List[EconomicEvent]] = {}

    def record(self, event: EconomicEvent) -> None:
        """Append an event snapshot to its timeline."""
        timeline = self._timeline.setdefault(event.event_id, [])
        # Avoid storing exact duplicates consecutively.
        if timeline and timeline[-1] == event:
            return
        timeline.append(event)

    def timeline(self, event_id: str) -> List[EconomicEvent]:
        return list(self._timeline.get(event_id, []))

    def revision_count(self, event_id: str) -> int:
        return max(0, len(self._timeline.get(event_id, [])) - 1)

    def latest(self, event_id: str):
        timeline = self._timeline.get(event_id, [])
        return timeline[-1] if timeline else None