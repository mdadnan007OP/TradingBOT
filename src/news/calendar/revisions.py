"""Event revision tracking and duplicate detection."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Tuple

from src.news.base import EventStatus
from src.news.models import EconomicEvent


def _dedup_key(event: EconomicEvent) -> str:
    """Stable dedup key: provider + currency + name + scheduled time."""
    ts = event.scheduled_time.isoformat() if event.scheduled_time else "unresolved"
    return f"{event.provider_id}|{event.currency}|{event.event_name.lower()}|{ts}"


def deduplicate_events(
    events: List[EconomicEvent],
) -> Tuple[List[EconomicEvent], List[EconomicEvent]]:
    """Return (unique_events, duplicates).

    Keeps the most recently updated record per dedup key.
    """
    seen: Dict[str, EconomicEvent] = {}
    duplicates: List[EconomicEvent] = []
    for event in events:
        key = _dedup_key(event)
        if key in seen:
            prev = seen[key]
            # Prefer the record with a later last_update / retrieval time.
            prev_ts = prev.last_update_time or prev.retrieval_time
            cur_ts = event.last_update_time or event.retrieval_time
            if cur_ts is not None and (prev_ts is None or cur_ts >= prev_ts):
                duplicates.append(prev)
                seen[key] = event
            else:
                duplicates.append(event)
        else:
            seen[key] = event
    return list(seen.values()), duplicates


def merge_revision(
    existing: EconomicEvent,
    new: EconomicEvent,
) -> EconomicEvent:
    """Merge a revised event into an existing record.

    Newer actual/forecast/previous values replace older ones; the merged record
    is marked REVISED. Never fabricates missing values.
    """
    if new.actual_value is not None:
        new_status = EventStatus.REVISED if existing.actual_value is not None else new.status
    else:
        new_status = new.status

    return EconomicEvent(
        event_id=existing.event_id,
        provider_id=existing.provider_id,
        country=existing.country,
        currency=existing.currency,
        event_name=existing.event_name,
        category=existing.category,
        importance=new.importance if new.importance != existing.importance else existing.importance,
        raw_importance=new.raw_importance or existing.raw_importance,
        scheduled_time=new.scheduled_time or existing.scheduled_time,
        scheduled_time_original=new.scheduled_time_original or existing.scheduled_time_original,
        original_timezone=new.original_timezone or existing.original_timezone,
        time_resolved=existing.time_resolved and new.time_resolved,
        actual_value=new.actual_value if new.actual_value is not None else existing.actual_value,
        forecast_value=new.forecast_value if new.forecast_value is not None else existing.forecast_value,
        previous_value=new.previous_value if new.previous_value is not None else existing.previous_value,
        revised_previous_value=new.revised_previous_value or existing.revised_previous_value,
        status=new_status,
        tentative_time=new.tentative_time or existing.tentative_time,
        all_day=new.all_day or existing.all_day,
        publication_time=new.publication_time or existing.publication_time,
        retrieval_time=new.retrieval_time or existing.retrieval_time,
        last_update_time=new.last_update_time or existing.last_update_time,
        source_provenance=new.source_provenance or existing.source_provenance,
        provider_freshness=new.provider_freshness or existing.provider_freshness,
    )