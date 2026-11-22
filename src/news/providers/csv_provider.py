"""CSV historical economic-calendar provider.

Loads events from a local CSV file. Validates required columns and does not
invent missing values. Useful for historical fixtures and backtesting.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.news.base import CalendarProvider
from src.news.models import EconomicEvent
from src.news.normalization import normalize_event

_REQUIRED_COLUMNS = {"event_name", "currency", "scheduled_time"}
_OPTIONAL_COLUMNS = {
    "event_id", "country", "importance", "actual", "forecast", "previous",
    "revised_previous", "status", "original_timezone", "source",
}


@dataclass
class CsvCalendarProvider(CalendarProvider):
    """Historical economic calendar provider reading a local CSV file."""

    path: str
    provider_id: str = "csv"
    is_simulated: bool = False

    def _load(self) -> List[Dict[str, str]]:
        if not os.path.isfile(self.path):
            return []
        rows: List[Dict[str, str]] = []
        with open(self.path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                return []
            missing = _REQUIRED_COLUMNS - set(reader.fieldnames)
            if missing:
                raise ValueError(
                    f"CSV calendar missing required columns: {sorted(missing)}"
                )
            for row in reader:
                rows.append({k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()})
        return rows

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
        currencies_upper = {c.upper() for c in currencies} if currencies else None
        events: List[EconomicEvent] = []
        for raw in self._load():
            # Parse scheduled_time from string.
            ts_raw = raw.get("scheduled_time")
            if ts_raw:
                try:
                    ts = datetime.fromisoformat(ts_raw)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                except ValueError:
                    ts = None
            else:
                ts = None
            payload: Dict = dict(raw)
            payload["scheduled_time"] = ts
            payload["retrieval_time"] = datetime.now(timezone.utc)
            # Provider freshness from file mtime.
            try:
                payload["provider_freshness"] = datetime.fromtimestamp(
                    os.path.getmtime(self.path), tz=timezone.utc
                )
            except OSError:
                payload["provider_freshness"] = None
            event = normalize_event(payload, self.provider_id)
            if currencies_upper is not None and event.currency.upper() not in currencies_upper:
                continue
            if event.scheduled_time is not None and not (start <= event.scheduled_time <= end):
                continue
            events.append(event)
        return events