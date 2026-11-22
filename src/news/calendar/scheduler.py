"""Scheduler: find relevant upcoming/recent events for an instrument."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from src.news.base import Importance
from src.news.config import NewsConfig
from src.news.calendar.event_mapping import instrument_is_relevant
from src.news.models import EconomicEvent, ImpactAssessment


def find_relevant_events(
    events: List[EconomicEvent],
    instrument: str,
    config: NewsConfig,
    now: Optional[datetime] = None,
    horizon: Optional[timedelta] = None,
) -> List[ImpactAssessment]:
    """Return impact assessments for events relevant to an instrument.

    Includes events whose scheduled time falls within [now - post, now + horizon]
    where post = configured post-window for their importance, and events that are
    unresolved-time but relevant (flagged separately by callers).
    """
    now = now or datetime.now(timezone.utc)
    horizon = horizon or timedelta(hours=24)
    results: List[ImpactAssessment] = []

    for event in events:
        if not instrument_is_relevant(instrument, event, config):
            continue
        if event.scheduled_time is None:
            # Unresolved time — include so callers can flag EVENT_TIME_UNCERTAIN.
            results.append(
                ImpactAssessment(
                    event=event,
                    relevant=True,
                    importance=event.importance,
                    category=event.category,
                    relevance_reason="unresolved_time",
                    time_until=None,
                    time_since=None,
                )
            )
            continue
        post = timedelta(minutes=config.get_window(event.importance, event.category).post_minutes)
        if now - post <= event.scheduled_time <= now + horizon:
            delta = event.scheduled_time - now
            time_until = delta if delta.total_seconds() >= 0 else None
            time_since = (-delta) if delta.total_seconds() < 0 else None
            results.append(
                ImpactAssessment(
                    event=event,
                    relevant=True,
                    importance=event.importance,
                    category=event.category,
                    relevance_reason="scheduled_within_window",
                    time_until=time_until,
                    time_since=time_since,
                )
            )
    return results


def next_event_for_instrument(
    events: List[EconomicEvent],
    instrument: str,
    config: NewsConfig,
    now: Optional[datetime] = None,
) -> Optional[ImpactAssessment]:
    """Return the nearest upcoming relevant event (or None)."""
    now = now or datetime.now(timezone.utc)
    assessments = find_relevant_events(events, instrument, config, now=now)
    upcoming = [
        a for a in assessments
        if a.time_until is not None
    ]
    if not upcoming:
        return None
    return min(upcoming, key=lambda a: a.time_until)