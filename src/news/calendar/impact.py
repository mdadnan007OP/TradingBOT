"""Impact classification for events against instruments.

Distinguishes scheduled event impact (provider rating + category) from actual
market reaction. Does NOT predict market direction from an event name.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from src.news.base import Importance
from src.news.config import NewsConfig
from src.news.calendar.event_mapping import instrument_is_relevant
from src.news.models import EconomicEvent, ImpactAssessment


def assess_impact(
    event: EconomicEvent,
    instrument: str,
    config: NewsConfig,
    now: Optional[datetime] = None,
) -> ImpactAssessment:
    """Assess an event's impact/relevance for an instrument.

    Importance comes from the provider rating (normalized) — never invented from
    the event name. Relevance comes from currency/category mapping.
    """
    now = now or datetime.now(timezone.utc)
    relevant = instrument_is_relevant(instrument, event, config)

    time_until = None
    time_since = None
    if event.scheduled_time is not None:
        delta = event.scheduled_time - now
        if delta.total_seconds() >= 0:
            time_until = delta
        else:
            time_since = -delta

    return ImpactAssessment(
        event=event,
        relevant=relevant,
        importance=event.importance,
        category=event.category,
        relevance_reason=(
            f"currency={event.currency} category={event.category.value}"
            if relevant else None
        ),
        time_until=time_until,
        time_since=time_since,
    )