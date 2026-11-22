"""Restriction builder: consolidates relevant events into a NewsRiskContext.

This is the bridge between the news engine and the Phase 6 Risk Management
Engine. It never trades; it only describes event-related restrictions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Sequence

from src.news.base import Importance, NewsWindowStatus, UnavailablePolicy
from src.news.config import NewsConfig
from src.news.filters.news_window import (
    compute_news_window_status,
    consolidate_windows,
)
from src.news.models import (
    EconomicEvent,
    ImpactAssessment,
    NewsRiskContext,
)


def _max_importance(assessments: Sequence[ImpactAssessment]) -> Importance:
    order = {
        Importance.UNKNOWN: 0,
        Importance.LOW: 1,
        Importance.MEDIUM: 2,
        Importance.HIGH: 3,
    }
    best = Importance.UNKNOWN
    best_rank = -1
    for a in assessments:
        rank = order.get(a.importance, 0)
        if rank > best_rank:
            best_rank = rank
            best = a.importance
    return best


def _nearest_time_fields(
    assessments: Sequence[ImpactAssessment],
    now: datetime,
):
    """Return (time_until_nearest, time_since_most_recent)."""
    time_until = None
    time_since = None
    for a in assessments:
        ev = a.event
        if ev.scheduled_time is None:
            continue
        delta = ev.scheduled_time - now
        if delta.total_seconds() >= 0:
            if time_until is None or delta < time_until:
                time_until = delta
        else:
            since = -delta
            if time_since is None or since < time_since:
                time_since = since
    return time_until, time_since


def build_news_risk_context(
    events: List[EconomicEvent],
    instrument: str,
    config: NewsConfig,
    now: Optional[datetime] = None,
    data_reliable: bool = True,
    unavailable_reason: Optional[str] = None,
) -> NewsRiskContext:
    """Build a NewsRiskContext for an instrument from candidate events.

    Args:
        events: Candidate events (already restricted to the instrument's relevant
            currencies by the caller, or a superset — relevance is applied here).
        instrument: The instrument symbol (e.g. ``"EURUSD"``).
        config: News engine configuration.
        now: Evaluation time (UTC).
        data_reliable: False when provider data is stale/unavailable.
        unavailable_reason: Reason string when data is unreliable.
    """
    now = now or datetime.now(timezone.utc)

    from src.news.filters.relevance import filter_relevant_events

    assessments = filter_relevant_events(events, instrument, config)
    relevant_ids = [a.event.event_id for a in assessments]
    categories = sorted({a.category for a in assessments}, key=lambda c: c.value)
    max_importance = _max_importance(assessments)
    time_until, time_since = _nearest_time_fields(assessments, now)

    if not data_reliable:
        if config.unavailable_policy == UnavailablePolicy.BLOCK_NEW_ENTRIES:
            window_status = NewsWindowStatus.NEWS_DATA_UNAVAILABLE
        else:
            # ALLOW_WITH_WARNING: still signal caution, but mark unreliable.
            window_status = NewsWindowStatus.NEWS_CAUTION
        return NewsRiskContext(
            instrument=instrument,
            relevant_event_ids=relevant_ids,
            max_importance=max_importance,
            categories=categories,
            time_until_event=time_until,
            time_since_release=time_since,
            window_status=window_status,
            data_reliable=False,
            restriction_reason=unavailable_reason
            or "News/calendar data unavailable or stale",
            evaluated_at=now,
        )

    window_status, reason = compute_news_window_status(assessments, config, now=now)

    return NewsRiskContext(
        instrument=instrument,
        relevant_event_ids=relevant_ids,
        max_importance=max_importance,
        categories=categories,
        time_until_event=time_until,
        time_since_release=time_since,
        window_status=window_status,
        data_reliable=True,
        restriction_reason=reason,
        evaluated_at=now,
    )