"""News & economic calendar data models.

All models are immutable frozen dataclasses. Timestamps are timezone-aware UTC
unless explicitly marked as unresolved (e.g. MQL5 server-tz cannot be verified).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from src.news.base import (
    EventCategory,
    EventStatus,
    Importance,
    NewsWindowStatus,
)


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize a datetime to timezone-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class EconomicEvent:
    """A standardized economic-calendar event.

    Never invent missing actual/forecast/previous values or event times. When
    the scheduled time cannot be resolved to UTC, ``time_resolved`` is False and
    ``scheduled_time`` may be None.
    """

    event_id: str
    provider_id: str
    country: str
    currency: str
    event_name: str
    category: EventCategory
    importance: Importance
    raw_importance: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    """UTC scheduled release time, or None if unresolved."""
    scheduled_time_original: Optional[datetime] = None
    """Original (pre-conversion) scheduled time as provided, for display."""
    original_timezone: Optional[str] = None
    """Original timezone identifier of the provider timestamp."""
    time_resolved: bool = True
    """False when the server timezone could not be verified (unresolved time)."""

    actual_value: Optional[str] = None
    forecast_value: Optional[str] = None
    previous_value: Optional[str] = None
    revised_previous_value: Optional[str] = None

    status: EventStatus = EventStatus.SCHEDULED
    tentative_time: bool = False
    all_day: bool = False

    publication_time: Optional[datetime] = None
    """UTC time the actual value was published, if available."""
    retrieval_time: Optional[datetime] = None
    """UTC time this record was retrieved/created."""
    last_update_time: Optional[datetime] = None
    """UTC time this record was last updated (revisions)."""

    source_provenance: str = ""
    provider_freshness: Optional[datetime] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "scheduled_time", _utc(self.scheduled_time))
        object.__setattr__(
            self, "scheduled_time_original",
            self.scheduled_time_original or self.scheduled_time,
        )
        object.__setattr__(self, "publication_time", _utc(self.publication_time))
        object.__setattr__(self, "retrieval_time", _utc(self.retrieval_time))
        object.__setattr__(self, "last_update_time", _utc(self.last_update_time))
        object.__setattr__(self, "provider_freshness", _utc(self.provider_freshness))

    @property
    def is_simulated(self) -> bool:
        return self.source_provenance.lower().startswith("simulated") or (
            self.source_provenance.lower().startswith("mock")
        )

    def is_relevant_to(self, currency: str) -> bool:
        return self.currency.upper() == currency.upper()


@dataclass(frozen=True)
class NewsArticle:
    """A normalized news article from a permitted source."""

    article_id: str
    source_name: str
    headline: str
    url: str
    published_time: Optional[datetime]
    retrieval_time: Optional[datetime]
    related_currencies: List[str] = field(default_factory=list)
    duplicate_key: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "published_time", _utc(self.published_time))
        object.__setattr__(self, "retrieval_time", _utc(self.retrieval_time))


@dataclass(frozen=True)
class ImpactAssessment:
    """Impact/relevance assessment for an event against an instrument."""

    event: EconomicEvent
    relevant: bool
    importance: Importance
    category: EventCategory
    relevance_reason: Optional[str] = None
    time_until: Optional[timedelta] = None
    time_since: Optional[timedelta] = None


@dataclass(frozen=True)
class NewsRiskContext:
    """Structured news context passed to the Phase 6 Risk Management Engine."""

    instrument: str
    relevant_event_ids: List[str] = field(default_factory=list)
    max_importance: Importance = Importance.UNKNOWN
    categories: List[EventCategory] = field(default_factory=list)
    time_until_event: Optional[timedelta] = None
    time_since_release: Optional[timedelta] = None
    window_status: NewsWindowStatus = NewsWindowStatus.NEWS_CLEAR
    provider_freshness: Optional[datetime] = None
    data_reliable: bool = True
    restriction_reason: Optional[str] = None
    evaluated_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evaluated_at", _utc(self.evaluated_at))

    @property
    def blocks_new_entries(self) -> bool:
        return self.window_status in (
            NewsWindowStatus.BLOCK_NEW_ENTRIES,
            NewsWindowStatus.EVENT_TIME_UNCERTAIN,
            NewsWindowStatus.NEWS_DATA_UNAVAILABLE,
        )

    @property
    def is_caution(self) -> bool:
        return self.window_status == NewsWindowStatus.NEWS_CAUTION

    def to_dict(self) -> Dict:
        return {
            "instrument": self.instrument,
            "relevant_event_ids": self.relevant_event_ids,
            "max_importance": self.max_importance.value,
            "categories": [c.value for c in self.categories],
            "time_until_event_seconds": (
                self.time_until_event.total_seconds()
                if self.time_until_event is not None else None
            ),
            "time_since_release_seconds": (
                self.time_since_release.total_seconds()
                if self.time_since_release is not None else None
            ),
            "window_status": self.window_status.value,
            "data_reliable": self.data_reliable,
            "restriction_reason": self.restriction_reason,
            "evaluated_at": self.evaluated_at.isoformat() if self.evaluated_at else None,
        }