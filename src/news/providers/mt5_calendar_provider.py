"""MetaTrader Economic Calendar bridge provider.

The MQL5 economic-calendar functions (``CalendarValueHistory`` etc.) are only
available inside MQL5, NOT through the official MetaTrader5 Python package.
This provider therefore reads an **MQL5-exported** file (JSON or CSV) produced
by a documented MQL5 script that runs inside the MT5 terminal.

Timezone requirement:
    MQL5 economic-calendar timestamps use **trading-server time**, NOT UTC.
    This provider preserves the server-time context and converts to UTC ONLY
    when a verified ``server_timezone`` is configured. If the server timezone
    cannot be determined reliably, ``time_resolved`` is False and the event
    time is treated as unresolved (preventing an apparently precise news-window
    restriction). It never silently assumes server timestamps are UTC.

Safety: read-only file access; never modifies the MT5 account or trade settings.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from src.news.base import CalendarProvider
from src.news.models import EconomicEvent
from src.news.normalization import normalize_event

# Columns produced by the documented MQL5 export script.
_MT5_FIELDS = {
    "event_id", "country", "currency", "event_name", "importance",
    "server_time", "actual", "forecast", "previous", "updated",
    "source",
}


@dataclass
class MT5CalendarProvider(CalendarProvider):
    """Reads MQL5-exported economic calendar data.

    Args:
        path: Path to the exported JSON or CSV file.
        provider_id: Provider identifier.
        server_timezone: Verified timezone of the MT5 trading server (e.g.
            ``"Europe/Berlin"``). ``None`` or ``"unknown"`` ⇒ unresolved time.
        is_simulated: Always False (genuine broker data).
    """

    path: str
    provider_id: str = "mt5_calendar"
    server_timezone: Optional[str] = None
    is_simulated: bool = False

    def _resolve_tz(self):
        if not self.server_timezone or self.server_timezone.lower() == "unknown":
            return None
        if ZoneInfo is None:
            return None
        try:
            return ZoneInfo(self.server_timezone)
        except Exception:
            return None

    def _load_records(self) -> List[Dict[str, Any]]:
        if not os.path.isfile(self.path):
            return []
        if self.path.lower().endswith(".json"):
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                data = data.get("events", [])
            return data if isinstance(data, list) else []
        # CSV fallback
        import csv

        with open(self.path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            return [dict(r) for r in reader]

    def _convert_server_time(self, raw: Any) -> tuple:
        """Convert a server-time string to (utc_datetime, resolved_bool)."""
        if raw is None or raw == "":
            return None, False
        if isinstance(raw, datetime):
            dt = raw
        else:
            try:
                dt = datetime.fromisoformat(str(raw))
            except ValueError:
                return None, False
        tz = self._resolve_tz()
        if tz is None:
            # Server timezone unverified: do NOT assume UTC. Mark unresolved.
            return None, False
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        else:
            dt = dt.astimezone(tz)
        return dt.astimezone(timezone.utc), True

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
        for rec in self._load_records():
            server_time_raw = rec.get("server_time")
            utc_dt, resolved = self._convert_server_time(server_time_raw)

            payload: Dict[str, Any] = {
                "event_id": rec.get("event_id"),
                "country": rec.get("country"),
                "currency": rec.get("currency"),
                "event_name": rec.get("event_name"),
                "importance": rec.get("importance"),
                "scheduled_time": utc_dt,
                "scheduled_time_original": server_time_raw,
                "original_timezone": self.server_timezone or "unknown",
                "time_resolved": resolved,
                "actual": rec.get("actual"),
                "forecast": rec.get("forecast"),
                "previous": rec.get("previous"),
                "updated": rec.get("updated"),
                "source": rec.get("source") or self.provider_id,
                "retrieval_time": datetime.now(timezone.utc),
                "provider_freshness": rec.get("updated"),
            }
            event = normalize_event(payload, self.provider_id)

            if currencies_upper is not None and event.currency.upper() not in currencies_upper:
                continue
            # Include unresolved-time events so callers can flag them, but only
            # if no currency filter excludes them.
            if event.scheduled_time is not None and not (start <= event.scheduled_time <= end):
                continue
            events.append(event)
        return events

    def last_update(self) -> Optional[datetime]:
        """Return the file modification time as a freshness signal."""
        try:
            return datetime.fromtimestamp(os.path.getmtime(self.path), tz=timezone.utc)
        except OSError:
            return None