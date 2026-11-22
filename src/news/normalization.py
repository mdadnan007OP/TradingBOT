"""Normalization of raw provider event data into standardized EconomicEvent.

Raw provider payloads differ in shape. This module maps common field names into
the canonical `EconomicEvent` model without inventing missing values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from src.news.base import EventCategory, EventStatus, Importance
from src.news.models import EconomicEvent
from src.news.registry import CategoryRegistry


_IMPORTANCE_MAP = {
    "high": Importance.HIGH,
    "medium": Importance.MEDIUM,
    "med": Importance.MEDIUM,
    "low": Importance.LOW,
    "unknown": Importance.UNKNOWN,
}


def normalize_importance(raw: Optional[Any]) -> Importance:
    """Normalize a raw importance value (str/int) to Importance."""
    if raw is None:
        return Importance.UNKNOWN
    if isinstance(raw, Importance):
        return raw
    if isinstance(raw, (int, float)):
        # Common providers: 3=high, 2=medium, 1=low
        if raw >= 3:
            return Importance.HIGH
        if raw == 2:
            return Importance.MEDIUM
        if raw == 1:
            return Importance.LOW
        return Importance.UNKNOWN
    key = str(raw).strip().lower()
    return _IMPORTANCE_MAP.get(key, Importance.UNKNOWN)


def _first_key(payload: Dict[str, Any], *keys: str) -> Optional[Any]:
    for k in keys:
        if k in payload and payload[k] is not None:
            return payload[k]
    return None


def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _str_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        if isinstance(value, Decimal) and value.is_nan():
            return None
    except Exception:
        pass
    s = str(value).strip()
    return s if s != "" else None


def normalize_event(
    raw: Dict[str, Any],
    provider_id: str,
    registry: Optional[CategoryRegistry] = None,
    retrieval_time: Optional[datetime] = None,
) -> EconomicEvent:
    """Map a raw provider payload dict into a canonical EconomicEvent.

    Missing values remain None — never invented.
    """
    registry = registry or CategoryRegistry()
    retrieval_time = retrieval_time or datetime.now(timezone.utc)

    event_id = _first_key(raw, "event_id", "id", "uid")
    event_id = str(event_id) if event_id is not None else f"{provider_id}:{_first_key(raw, 'name', 'event_name')}"

    event_name = _first_key(raw, "event_name", "name", "title") or ""
    currency = _first_key(raw, "currency", "related_currency", "ccy") or ""
    country = _first_key(raw, "country", "country_code", "region") or ""

    raw_importance = _first_key(raw, "importance", "impact", "priority")
    importance = normalize_importance(raw_importance)

    scheduled = _first_key(raw, "scheduled_time", "time", "date", "utc_time")
    scheduled_utc = _to_utc(scheduled)
    time_resolved = _first_key(raw, "time_resolved", "tz_verified")
    time_resolved = bool(time_resolved) if time_resolved is not None else True
    if scheduled_utc is None:
        time_resolved = False

    original_tz = _first_key(raw, "original_timezone", "timezone", "tz")

    actual = _first_key(raw, "actual", "actual_value", "actuals")
    forecast = _first_key(raw, "forecast", "forecast_value", "consensus")
    previous = _first_key(raw, "previous", "previous_value", "prior")
    revised = _first_key(raw, "revised_previous", "revised_previous_value")

    status_raw = _first_key(raw, "status")
    try:
        status = EventStatus(str(status_raw).upper()) if status_raw else EventStatus.SCHEDULED
    except ValueError:
        status = EventStatus.SCHEDULED

    tentative = bool(_first_key(raw, "tentative", "tentative_time") or False)
    all_day = bool(_first_key(raw, "all_day", "allday") or False)

    publication = _to_utc(_first_key(raw, "publication_time", "published_at"))
    last_update = _to_utc(_first_key(raw, "last_update", "updated_at"))

    source = _first_key(raw, "source", "source_provenance", "provider") or provider_id

    return EconomicEvent(
        event_id=event_id,
        provider_id=provider_id,
        country=str(country),
        currency=str(currency).upper(),
        event_name=str(event_name),
        category=registry.classify(str(event_name)),
        importance=importance,
        raw_importance=str(raw_importance) if raw_importance is not None else None,
        scheduled_time=scheduled_utc,
        scheduled_time_original=scheduled,
        original_timezone=str(original_tz) if original_tz is not None else None,
        time_resolved=time_resolved,
        actual_value=_str_or_none(actual),
        forecast_value=_str_or_none(forecast),
        previous_value=_str_or_none(previous),
        revised_previous_value=_str_or_none(revised),
        status=status,
        tentative_time=tentative,
        all_day=all_day,
        publication_time=publication,
        retrieval_time=retrieval_time,
        last_update_time=last_update,
        source_provenance=str(source),
        provider_freshness=_to_utc(_first_key(raw, "provider_freshness", "freshness")),
    )