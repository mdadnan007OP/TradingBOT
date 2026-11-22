"""News-window engine.

Computes pre/post-event restriction windows and consolidates overlapping events
into a single status for an instrument. Uses UTC internally with timezone-aware
calculations. Unresolved event times produce EVENT_TIME_UNCERTAIN (never a
precise window).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from src.news.base import Importance, NewsWindowStatus
from src.news.config import NewsConfig
from src.news.models import EconomicEvent, ImpactAssessment


def _event_status(
    event: EconomicEvent,
    config: NewsConfig,
    now: datetime,
) -> Optional[NewsWindowStatus]:
    """Return the window status for a single relevant event, or None if outside."""
    if event.scheduled_time is None or not event.time_resolved:
        # Unresolved time — cannot produce a precise window; flag uncertainty.
        return NewsWindowStatus.EVENT_TIME_UNCERTAIN

    window = config.get_window(event.importance, event.category)
    pre = timedelta(minutes=window.pre_minutes)
    post = timedelta(minutes=window.post_minutes)
    event_time = event.scheduled_time

    if event_time - pre <= now <= event_time + post:
        # Within restriction window.
        if event.importance == Importance.HIGH:
            return NewsWindowStatus.BLOCK_NEW_ENTRIES
        if event.importance == Importance.MEDIUM:
            return NewsWindowStatus.BLOCK_NEW_ENTRIES
        # LOW impact → caution only (if configured caution_importance met)
        order = {Importance.LOW: 0, Importance.MEDIUM: 1, Importance.HIGH: 2, Importance.UNKNOWN: 0}
        if order.get(event.importance, 0) >= order.get(config.caution_importance, 1):
            return NewsWindowStatus.NEWS_CAUTION
        return None
    return None


def compute_news_window_status(
    assessments: List[ImpactAssessment],
    config: NewsConfig,
    now: Optional[datetime] = None,
) -> Tuple[NewsWindowStatus, Optional[str]]:
    """Compute a single consolidated status from relevant events.

    Returns (status, reason). Precedence:
      EVENT_TIME_UNCERTAIN > NEWS_DATA_UNAVAILABLE (handled by caller) >
      BLOCK_NEW_ENTRIES > NEWS_CAUTION > NEWS_CLEAR.
    """
    now = now or datetime.now(timezone.utc)
    statuses = []
    for a in assessments:
        st = _event_status(a.event, config, now)
        if st is not None:
            statuses.append(st)

    if NewsWindowStatus.EVENT_TIME_UNCERTAIN in statuses:
        return (
            NewsWindowStatus.EVENT_TIME_UNCERTAIN,
            "One or more relevant events have unresolved scheduled time",
        )
    if NewsWindowStatus.BLOCK_NEW_ENTRIES in statuses:
        blocking = [
            a.event.event_name for a in assessments
            if _event_status(a.event, config, now) == NewsWindowStatus.BLOCK_NEW_ENTRIES
        ]
        return (
            NewsWindowStatus.BLOCK_NEW_ENTRIES,
            f"High/medium impact event window: {', '.join(blocking)}",
        )
    if NewsWindowStatus.NEWS_CAUTION in statuses:
        return (
            NewsWindowStatus.NEWS_CAUTION,
            "Approaching a lower-impact event window",
        )
    return NewsWindowStatus.NEWS_CLEAR, None


def consolidate_windows(
    statuses: List[NewsWindowStatus],
) -> NewsWindowStatus:
    """Consolidate multiple statuses into one using precedence."""
    precedence = [
        NewsWindowStatus.EVENT_TIME_UNCERTAIN,
        NewsWindowStatus.NEWS_DATA_UNAVAILABLE,
        NewsWindowStatus.BLOCK_NEW_ENTRIES,
        NewsWindowStatus.NEWS_CAUTION,
        NewsWindowStatus.NEWS_CLEAR,
    ]
    for st in precedence:
        if st in statuses:
            return st
    return NewsWindowStatus.NEWS_CLEAR