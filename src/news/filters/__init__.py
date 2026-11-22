"""Filters package: relevance, news windows, restrictions."""

from __future__ import annotations

from src.news.filters.relevance import (
    filter_relevant_events,
    relevant_events_for_instrument,
)
from src.news.filters.news_window import (
    compute_news_window_status,
    consolidate_windows,
)
from src.news.filters.restriction import build_news_risk_context

__all__ = [
    "filter_relevant_events",
    "relevant_events_for_instrument",
    "compute_news_window_status",
    "consolidate_windows",
    "build_news_risk_context",
]