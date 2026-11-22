"""News & Economic Calendar Engine base module.

Phase 7 is a news/risk-information phase only. It collects, normalizes and
evaluates economic-calendar events and news, and communicates event-related
restrictions to the Phase 6 Risk Management Engine. It never places, modifies
or closes orders and never executes trades.
"""

from __future__ import annotations

import abc
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import List, Optional

ABC = abc.ABC
abstractmethod = abc.abstractmethod


class Importance(str, Enum):
    """Normalized event importance."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class EventStatus(str, Enum):
    """Lifecycle status of an economic event."""

    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    PUBLISHED = "PUBLISHED"
    REVISED = "REVISED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class NewsWindowStatus(str, Enum):
    """Consolidated news-window restriction status for an instrument."""

    NEWS_CLEAR = "NEWS_CLEAR"
    NEWS_CAUTION = "NEWS_CAUTION"
    BLOCK_NEW_ENTRIES = "BLOCK_NEW_ENTRIES"
    EVENT_TIME_UNCERTAIN = "EVENT_TIME_UNCERTAIN"
    NEWS_DATA_UNAVAILABLE = "NEWS_DATA_UNAVAILABLE"


class EventCategory(str, Enum):
    """Economic event category."""

    INFLATION = "INFLATION"
    EMPLOYMENT = "EMPLOYMENT"
    CENTRAL_BANK = "CENTRAL_BANK"
    GROWTH = "GROWTH"
    COMMODITIES = "COMMODITIES"
    OTHER = "OTHER"


class UnavailablePolicy(str, Enum):
    """Policy when news/calendar data is unavailable or stale."""

    BLOCK_NEW_ENTRIES = "BLOCK_NEW_ENTRIES"
    ALLOW_WITH_WARNING = "ALLOW_WITH_WARNING"


class CalendarProvider(ABC):
    """Abstract interface for economic-calendar providers."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        ...

    @property
    @abstractmethod
    def is_simulated(self) -> bool:
        ...

    @abstractmethod
    def get_events(
        self,
        start: datetime,
        end: datetime,
        currencies: Optional[List[str]] = None,
    ) -> list:
        """Return normalized events in the [start, end] window (UTC)."""
        ...


class NewsProvider(ABC):
    """Abstract interface for news providers."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        ...

    @property
    @abstractmethod
    def is_simulated(self) -> bool:
        ...

    @abstractmethod
    def get_articles(
        self,
        start: datetime,
        end: datetime,
    ) -> list:
        """Return news articles in the [start, end] window (UTC)."""
        ...


class NewsEngineABC(ABC):
    """Abstract interface for the news service."""

    @abstractmethod
    def events_in_window(self, start: datetime, end: datetime) -> list:
        ...

    @abstractmethod
    def risk_context(self, instrument: str, now: Optional[datetime] = None):
        ...