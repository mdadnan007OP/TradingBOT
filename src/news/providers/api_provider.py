"""Optional external economic-calendar API provider interface.

This is a provider **interface**, not a live integration. Choosing an API,
its access plan, rate limits and licensing must be investigated and approved
before wiring a real client. Normal project tests do NOT require a paid API.

Credentials are read ONLY from environment variables and never committed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.news.base import CalendarProvider
from src.news.models import EconomicEvent
from src.news.normalization import normalize_event


@dataclass
class ApiCalendarProvider(CalendarProvider):
    """Authorized economic-calendar API provider (interface stub).

    Subclasses implement ``_fetch_raw`` against a licensed API. The base class
    normalizes raw payloads into ``EconomicEvent``.
    """

    provider_id: str = "api"
    api_key_env: str = "NEWS_API_KEY"
    base_url: str = ""
    is_simulated: bool = False

    def _api_key(self) -> Optional[str]:
        return os.environ.get(self.api_key_env)

    def _fetch_raw(
        self,
        start: datetime,
        end: datetime,
        currencies: Optional[List[str]] = None,
    ) -> List[Dict]:
        """Return raw event dicts from the API. Override in subclasses.

        Returns an empty list by default (no live integration).
        """
        return []

    def get_events(
        self,
        start: datetime,
        end: datetime,
        currencies: Optional[List[str]] = None,
    ) -> List[EconomicEvent]:
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        raw = self._fetch_raw(start, end, currencies)
        return [normalize_event(r, self.provider_id) for r in raw]