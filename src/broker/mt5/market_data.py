"""MT5 market data retrieval (read-only)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from src.market_data.models import (
    MarketTimeframe,
    MarketQuote,
    OHLCBar,
    DataSource,
)
from src.broker.mt5.connection import MT5ConnectionManager
from src.broker.mt5.exceptions import MT5DataError

logger = logging.getLogger(__name__)


# MT5 timeframe constants
MT5_TIMEFRAME_MAP = {
    MarketTimeframe.M1: 1,      # PERIOD_M1
    MarketTimeframe.M5: 5,      # PERIOD_M5
    MarketTimeframe.M15: 15,    # PERIOD_M15
    MarketTimeframe.M30: 30,    # PERIOD_M30
    MarketTimeframe.H1: 60,     # PERIOD_H1
    MarketTimeframe.H4: 240,    # PERIOD_H4
    MarketTimeframe.D1: 1440,   # PERIOD_D1
    MarketTimeframe.W1: 10080,  # PERIOD_W1
    MarketTimeframe.MN1: 43200, # PERIOD_MN1
}


class MT5MarketData:
    """Read-only market data retrieval from MT5 terminal."""

    def __init__(
        self,
        connection: MT5ConnectionManager,
        symbol_mapping: dict,
    ) -> None:
        """Initialize market data retriever.

        Args:
            connection: MT5 connection manager.
            symbol_mapping: Dict mapping canonical symbols to broker symbols.
        """
        self._connection = connection
        self._symbol_mapping = symbol_mapping
        self._mt5 = connection._mt5_module

    def _get_broker_symbol(self, canonical: str) -> Optional[str]:
        """Get broker symbol for a canonical symbol."""
        return self._symbol_mapping.get(canonical)

    def _convert_timeframe(self, tf: MarketTimeframe) -> int:
        """Convert MarketTimeframe to MT5 timeframe constant."""
        mt5_tf = MT5_TIMEFRAME_MAP.get(tf)
        if mt5_tf is None:
            raise ValueError(f"Unsupported timeframe: {tf}")
        return mt5_tf

    def get_quote(self, canonical_symbol: str) -> Optional[MarketQuote]:
        """Get current bid/ask quote for a symbol.

        Args:
            canonical_symbol: Internal canonical symbol (e.g., "EURUSD").

        Returns:
            MarketQuote with bid, ask, timestamp, or None if unavailable.
        """
        if not self._connection.check_connection():
            logger.warning("MT5 not connected for quote request")
            return None

        broker_symbol = self._get_broker_symbol(canonical_symbol)
        if broker_symbol is None:
            logger.warning("No broker symbol mapping for: %s", canonical_symbol)
            return None

        try:
            tick = self._mt5.symbol_info_tick(broker_symbol)
            if tick is None:
                error = self._mt5.last_error()
                logger.warning("Failed to get tick for %s: %s", broker_symbol, error)
                return None

            # MT5 timestamp is UTC
            timestamp = datetime.fromtimestamp(tick.time, tz=timezone.utc)

            return MarketQuote(
                symbol=canonical_symbol,
                timestamp=timestamp,
                bid=Decimal(str(tick.bid)),
                ask=Decimal(str(tick.ask)),
                last=Decimal(str(tick.last)) if tick.last > 0 else None,
                volume=tick.volume if tick.volume > 0 else None,
            )

        except Exception as exc:
            logger.exception("Error getting quote for %s: %s", canonical_symbol, exc)
            raise MT5DataError(f"Quote retrieval failed: {exc}") from exc

    def get_candles(
        self,
        canonical_symbol: str,
        timeframe: MarketTimeframe,
        start_time: datetime,
        end_time: datetime,
        completed_only: bool = True,
    ) -> List[OHLCBar]:
        """Get historical OHLC candles from MT5.

        Args:
            canonical_symbol: Internal canonical symbol.
            timeframe: Candle timeframe.
            start_time: Start time (inclusive), timezone-aware UTC.
            end_time: End time (inclusive), timezone-aware UTC.
            completed_only: If True, exclude the current forming candle (position 0).
                           If False, include all candles including position 0.

        Returns:
            List of OHLCBar objects, sorted chronologically.

        Raises:
            MT5DataError: If data retrieval fails.
        """
        if not self._connection.check_connection():
            logger.warning("MT5 not connected for candle request")
            return []

        broker_symbol = self._get_broker_symbol(canonical_symbol)
        if broker_symbol is None:
            logger.warning("No broker symbol mapping for: %s", canonical_symbol)
            return []

        mt5_tf = self._convert_timeframe(timeframe)

        try:
            # Convert datetime to UTC timestamp
            from_ts = int(start_time.timestamp())
            to_ts = int(end_time.timestamp())

            # Get rates from MT5. copy_rates_range returns bars ordered from
            # oldest to newest. The current forming candle may be included as
            # the newest bar if end_time is in the present.
            rates = self._mt5.copy_rates_range(
                broker_symbol,
                mt5_tf,
                from_ts,
                to_ts,
            )

            if rates is None:
                error = self._mt5.last_error()
                logger.warning("Failed to get rates for %s: %s", broker_symbol, error)
                return []

            # Sort defensively by time (oldest -> newest).
            rates = sorted(rates, key=lambda r: r['time'])

            tf_minutes = timeframe.minutes
            now_ts = datetime.now(timezone.utc).timestamp()

            bars = []
            for rate in rates:
                timestamp = datetime.fromtimestamp(rate['time'], tz=timezone.utc)

                # A bar is still forming when its period end lies in the future.
                period_end = rate['time'] + tf_minutes * 60
                is_forming = period_end > now_ts

                if completed_only and is_forming:
                    # Never silently classify an unfinished candle as complete.
                    continue

                bar = OHLCBar(
                    symbol=canonical_symbol,
                    timeframe=timeframe,
                    timestamp=timestamp,
                    open=Decimal(str(rate['open'])),
                    high=Decimal(str(rate['high'])),
                    low=Decimal(str(rate['low'])),
                    close=Decimal(str(rate['close'])),
                    tick_volume=int(rate['tick_volume']) if rate['tick_volume'] > 0 else None,
                    real_volume=int(rate['real_volume']) if rate['real_volume'] > 0 else None,
                    spread=int(rate['spread']) if rate['spread'] > 0 else None,
                    is_complete=not is_forming,
                    data_source=DataSource.LIVE,
                )
                bars.append(bar)

            return bars

        except Exception as exc:
            logger.exception("Error getting candles for %s: %s", canonical_symbol, exc)
            raise MT5DataError(f"Candle retrieval failed: {exc}") from exc

    def get_latest_candle(
        self,
        canonical_symbol: str,
        timeframe: MarketTimeframe,
        completed_only: bool = True,
    ) -> Optional[OHLCBar]:
        """Get the most recent candle for a symbol.

        Args:
            canonical_symbol: Internal canonical symbol.
            timeframe: Candle timeframe.
            completed_only: If True, return the last completed candle (position 1).
                           If False, return the current forming candle (position 0).

        Returns:
            OHLCBar or None if unavailable.
        """
        if not self._connection.check_connection():
            return None

        broker_symbol = self._get_broker_symbol(canonical_symbol)
        if broker_symbol is None:
            return None

        mt5_tf = self._convert_timeframe(timeframe)

        try:
            # Get up to 2 candles: position 0 (current forming) and position 1
            # (last completed). For completed-only retrieval we start at
            # position 1 per MT5 semantics.
            if completed_only:
                rates = self._mt5.copy_rates_from_pos(broker_symbol, mt5_tf, 1, 1)
                if rates is None or len(rates) == 0:
                    # Fall back to fetching two bars and filtering.
                    rates = self._mt5.copy_rates_from_pos(broker_symbol, mt5_tf, 0, 2)
            else:
                rates = self._mt5.copy_rates_from_pos(broker_symbol, mt5_tf, 0, 1)

            if rates is None or len(rates) == 0:
                return None

            # Sort defensively by time (oldest -> newest).
            rates = sorted(rates, key=lambda r: r['time'])
            tf_minutes = timeframe.minutes
            now_ts = datetime.now(timezone.utc).timestamp()

            selected = None
            if completed_only:
                # Newest bar whose period end is not in the future.
                for rate in reversed(rates):
                    if rate['time'] + tf_minutes * 60 <= now_ts:
                        selected = rate
                        break
                if selected is None:
                    return None
                is_complete = True
            else:
                # Current forming candle (position 0 / newest bar).
                selected = rates[-1]
                is_complete = False

            timestamp = datetime.fromtimestamp(selected['time'], tz=timezone.utc)

            return OHLCBar(
                symbol=canonical_symbol,
                timeframe=timeframe,
                timestamp=timestamp,
                open=Decimal(str(selected['open'])),
                high=Decimal(str(selected['high'])),
                low=Decimal(str(selected['low'])),
                close=Decimal(str(selected['close'])),
                tick_volume=int(selected['tick_volume']) if selected['tick_volume'] > 0 else None,
                real_volume=int(selected['real_volume']) if selected['real_volume'] > 0 else None,
                spread=int(selected['spread']) if selected['spread'] > 0 else None,
                is_complete=is_complete,
                data_source=DataSource.LIVE,
            )

        except Exception as exc:
            logger.exception("Error getting latest candle for %s: %s", canonical_symbol, exc)
            return None

    def get_historical_ticks(
        self,
        canonical_symbol: str,
        start_time: datetime,
        end_time: datetime,
        count: int = 1000,
    ) -> List[dict]:
        """Get historical ticks from MT5 (optional interface).

        Args:
            canonical_symbol: Internal canonical symbol.
            start_time: Start time (inclusive), timezone-aware UTC.
            end_time: End time (inclusive), timezone-aware UTC.
            count: Maximum number of ticks to retrieve.

        Returns:
            List of tick dictionaries with bid, ask, last, volume, timestamp.
        """
        if not self._connection.check_connection():
            return []

        broker_symbol = self._get_broker_symbol(canonical_symbol)
        if broker_symbol is None:
            return []

        try:
            from_ts = int(start_time.timestamp())
            to_ts = int(end_time.timestamp())

            ticks = self._mt5.copy_ticks_range(
                broker_symbol,
                from_ts,
                to_ts,
                self._mt5.COPY_TICKS_ALL,
            )

            if ticks is None:
                return []

            result = []
            for tick in ticks[:count]:
                result.append({
                    'timestamp': datetime.fromtimestamp(tick['time'], tz=timezone.utc),
                    'bid': Decimal(str(tick['bid'])),
                    'ask': Decimal(str(tick['ask'])),
                    'last': Decimal(str(tick['last'])) if tick['last'] > 0 else None,
                    'volume': tick['volume'] if tick['volume'] > 0 else None,
                    'flags': tick['flags'],
                })

            return result

        except Exception as exc:
            logger.exception("Error getting historical ticks for %s: %s", canonical_symbol, exc)
            return []