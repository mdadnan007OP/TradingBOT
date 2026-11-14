"""Market session awareness for market data validation.

Provides session calendars that distinguish expected market closures
(e.g. Forex weekends) from unexpected missing candles. All internal
timestamps are timezone-aware UTC.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.market_data.models import InstrumentType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketSession:
    """Description of a trading session for an instrument class.

    Attributes:
        session_id: Unique session identifier (e.g. ``forex``, ``crypto``).
        description: Human-readable description.
        is_24h: True if the market trades continuously (e.g. crypto).
        weekend_days: Set of weekday numbers (0=Mon ... 6=Sun) that are closed.
        daily_open_utc: Daily open time in UTC, if applicable.
        daily_close_utc: Daily close time in UTC, if applicable.
        timezone: IANA timezone name for the session's primary market.
    """

    session_id: str
    description: str
    is_24h: bool = False
    weekend_days: frozenset[int] = field(default_factory=lambda: frozenset({5, 6}))
    daily_open_utc: Optional[str] = None  # "HH:MM"
    daily_close_utc: Optional[str] = None  # "HH:MM"
    timezone: Optional[str] = None


# Default session calendars for major instrument classes.
# These are sensible defaults and should be overridden with broker-specific
# schedules during Phase 3 broker integration.
DEFAULT_SESSIONS: dict[str, MarketSession] = {
    "forex": MarketSession(
        session_id="forex",
        description="Forex market (Sunday 17:00 ET to Friday 17:00 ET)",
        is_24h=False,
        weekend_days=frozenset({5, 6}),  # Saturday, Sunday
        daily_open_utc="22:00",
        daily_close_utc="22:00",
        timezone="America/New_York",
    ),
    "metals": MarketSession(
        session_id="metals",
        description="Precious metals (near 24h, weekend closures vary)",
        is_24h=False,
        weekend_days=frozenset({5, 6}),
        daily_open_utc="23:00",
        daily_close_utc="22:00",
        timezone="America/New_York",
    ),
    "energy": MarketSession(
        session_id="energy",
        description="Energy commodities (CME Globex schedule)",
        is_24h=False,
        weekend_days=frozenset({5, 6}),
        daily_open_utc="18:00",
        daily_close_utc="17:00",
        timezone="America/Chicago",
    ),
    "indices": MarketSession(
        session_id="indices",
        description="Stock index futures (CME Globex schedule)",
        is_24h=False,
        weekend_days=frozenset({5, 6}),
        daily_open_utc="18:00",
        daily_close_utc="17:00",
        timezone="America/Chicago",
    ),
    "crypto": MarketSession(
        session_id="crypto",
        description="Cryptocurrency market (24/7/365)",
        is_24h=True,
        weekend_days=frozenset(),
        timezone="UTC",
    ),
    "equity": MarketSession(
        session_id="equity",
        description="Equity market (regular trading hours)",
        is_24h=False,
        weekend_days=frozenset({5, 6}),
        daily_open_utc="14:30",
        daily_close_utc="21:00",
        timezone="America/New_York",
    ),
}


class SessionCalendar:
    """Determines whether a market is open at a given UTC timestamp.

    Uses session definitions to distinguish expected closures (weekends,
    daily breaks) from unexpected data gaps.
    """

    def __init__(self, sessions: Optional[dict[str, MarketSession]] = None) -> None:
        self.sessions: dict[str, MarketSession] = sessions or dict(DEFAULT_SESSIONS)

    def get_session(self, session_id: str) -> Optional[MarketSession]:
        """Return the session definition for ``session_id``, or None."""
        return self.sessions.get(session_id)

    def is_market_open(
        self,
        session_id: str,
        timestamp: datetime,
    ) -> bool:
        """Return True if the market is open at ``timestamp`` (UTC-aware).

        For 24h markets (e.g. crypto), always returns True (except configured
        weekend days). For session-based markets, checks daily open/close
        and weekend closures.
        """
        session = self.get_session(session_id)
        if session is None:
            # Unknown session: assume open to avoid false positives.
            return True

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        weekday = timestamp.weekday()

        # 24h markets (e.g. crypto): closed only on configured weekend days.
        if session.is_24h:
            return weekday not in session.weekend_days

        # Weekend day check.
        if weekday in session.weekend_days:
            # Sunday: may open at daily_open_utc (Forex opens Sunday 22:00 UTC).
            if weekday == 6 and session.daily_open_utc is not None:
                open_h, open_m = map(int, session.daily_open_utc.split(":"))
                open_time = timestamp.replace(
                    hour=open_h, minute=open_m, second=0, microsecond=0
                )
                if timestamp >= open_time:
                    return True
            return False

        # Friday close: Forex-style markets close for the weekend at
        # daily_close_utc on Friday.
        if weekday == 4 and session.daily_close_utc is not None:
            close_h, close_m = map(int, session.daily_close_utc.split(":"))
            close_time = timestamp.replace(
                hour=close_h, minute=close_m, second=0, microsecond=0
            )
            if timestamp >= close_time:
                return False

        # Daily open/close check for weekdays.
        if session.daily_open_utc is not None and session.daily_close_utc is not None:
            open_h, open_m = map(int, session.daily_open_utc.split(":"))
            close_h, close_m = map(int, session.daily_close_utc.split(":"))
            open_time = timestamp.replace(
                hour=open_h, minute=open_m, second=0, microsecond=0
            )
            close_time = timestamp.replace(
                hour=close_h, minute=close_m, second=0, microsecond=0
            )

            if close_time <= open_time:
                # Overnight session (crosses midnight).
                return timestamp >= open_time or timestamp < close_time
            else:
                # Regular daytime session.
                return open_time <= timestamp < close_time

        # No daily constraints: open (weekend already handled above).
        return True

    def is_expected_closure(
        self,
        session_id: str,
        timestamp: datetime,
    ) -> bool:
        """Return True if the market is expected to be closed at ``timestamp``."""
        return not self.is_market_open(session_id, timestamp)

    def register_session(self, session_id: str, session: MarketSession) -> None:
        """Register or override a session definition."""
        self.sessions[session_id] = session
        logger.info("Registered market session: %s (%s)", session_id, session.description)

    def session_for_instrument_type(
        self,
        instrument_type,
    ) -> Optional[MarketSession]:
        """Map an InstrumentType to its default session."""
        mapping = {
            "forex": "forex",
            "metal": "metals",
            "energy": "energy",
            "index": "indices",
            "equity": "equity",
            "crypto": "crypto",
            "other": "forex",
        }
        session_id = mapping.get(str(instrument_type), "forex")
        return self.get_session(session_id)
