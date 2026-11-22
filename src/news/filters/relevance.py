"""Relevance filtering: which events matter for an instrument."""

from __future__ import annotations

from typing import List, Optional

from src.news.base import Importance
from src.news.config import NewsConfig
from src.news.calendar.impact import assess_impact
from src.news.models import EconomicEvent, ImpactAssessment


def filter_relevant_events(
    events: List[EconomicEvent],
    instrument: str,
    config: NewsConfig,
    min_importance: Optional[Importance] = Importance.LOW,
) -> List[ImpactAssessment]:
    """Return impact assessments for events relevant to an instrument."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    assessments: List[ImpactAssessment] = []
    for event in events:
        a = assess_impact(event, instrument, config, now=now)
        if a.relevant:
            if min_importance is not None:
                order = {Importance.LOW: 0, Importance.MEDIUM: 1, Importance.HIGH: 2, Importance.UNKNOWN: 3}
                if order.get(a.importance, 3) < order.get(min_importance, 0):
                    continue
            assessments.append(a)
    return assessments


def relevant_events_for_instrument(
    events: List[EconomicEvent],
    instrument: str,
    config: NewsConfig,
) -> List[EconomicEvent]:
    """Return the events (not assessments) relevant to an instrument."""
    return [a.event for a in filter_relevant_events(events, instrument, config)]