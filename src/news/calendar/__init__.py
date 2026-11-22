"""Calendar subpackage: event mapping, impact, scheduler, revisions."""

from __future__ import annotations

from src.news.calendar.event_mapping import (
    currencies_for_instrument,
    instrument_is_relevant,
)
from src.news.calendar.impact import assess_impact
from src.news.calendar.scheduler import (
    find_relevant_events,
    next_event_for_instrument,
)
from src.news.calendar.revisions import deduplicate_events, merge_revision

__all__ = [
    "currencies_for_instrument",
    "instrument_is_relevant",
    "assess_impact",
    "find_relevant_events",
    "next_event_for_instrument",
    "deduplicate_events",
    "merge_revision",
]