"""Adapters for passing news context into the Phase 6 Risk Management Engine.

Provides a concise human/machine-readable summary and a decision hint. The
RiskEngine itself applies the blocking policy; this module only summarizes.
"""

from __future__ import annotations

from typing import Dict

from src.news.base import NewsWindowStatus
from src.news.models import NewsRiskContext


def summarize_news_context(context: NewsRiskContext) -> Dict:
    """Return a compact dict summarizing the news restriction for logging.

    This never trades; it only describes the restriction so the risk engine and
    operators can see why new entries may be blocked.
    """
    return {
        "instrument": context.instrument,
        "window_status": context.window_status.value,
        "blocks_new_entries": context.blocks_new_entries,
        "is_caution": context.is_caution,
        "max_importance": context.max_importance.value,
        "relevant_event_ids": context.relevant_event_ids,
        "data_reliable": context.data_reliable,
        "restriction_reason": context.restriction_reason,
        "time_until_event_seconds": (
            context.time_until_event.total_seconds()
            if context.time_until_event is not None else None
        ),
        "time_since_release_seconds": (
            context.time_since_release.total_seconds()
            if context.time_since_release is not None else None
        ),
        "window_status_is_clear": context.window_status == NewsWindowStatus.NEWS_CLEAR,
    }