"""Mock market data provider.

Generates simulated OHLC candles using a seeded random walk. All output is
explicitly labeled as simulated and must never be presented as genuine market
prices. Safe for development and testing without any broker or market
connection.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from src.config import CONFIG
from src.market_data.base import MarketDataProvider
from src.market_data.models import (
    DataSource,
    DEFAULT_SYMBOLS,
    DEFAULT_INSTRUMENT_SPECS,
    InstrumentSpec,
    MarketQuote,
    MarketSymbol,
    MarketTimeframe,
    OHLCBar,
)

logger = logging.getLogger(__name__)


class MockMarketDataProvider(MarketDataProvider):
    """In-memory mock market data provider.

    Generates synthetic OHLC bars via a seeded geometric random walk. The
    provider is explicitly simulated: all prices are marked
    ``data_source=DataSource.SIMULATED`` and the provider name includes the
    ``Simulated`` prefix.

    Attributes:
        seed: Random seed for reproducibility. Defaults to 42.
        base_prices: Optional override map of symbol -> starting price.
        volatility: Price volatility per step (decimal fraction).
        instrument_specs: Optional map of symbol -> InstrumentSpec.
    """

    def __init__(
        self,
        seed: int = 42,
        base_prices: Optional[Dict[str, Decimal]] = None,
        volatility: Decimal = Decimal("0.001"),
        instrument_specs: Optional[Dict[str, InstrumentSpec]] = None,
    ) -> None:
        self._seed = seed
        self._rng = random.Random(seed)
        self._connected = False
        self._volatility = volatility
        self._base_prices: Dict[str, Decimal] = base_prices or {
            "XAUUSD": Decimal("2000.00"),
            "XAGUSD": Decimal("25.00"),
            "EURUSD": Decimal("1.0850"),
            "GBPUSD": Decimal("1.2700"),
            "USDJPY": Decimal("148.50"),
            "AUDUSD": Decimal("0.6500"),
            "USDCAD": Decimal("1.3500"),
            "WTIUSD": Decimal("75.00"),
            "BRENTUSD": Decimal("80.00"),
            "NAS100": Decimal("15000.00"),
            "BTCUSD": Decimal("60000.00"),
            "ETHUSD": Decimal("3000.00"),
        }
        self._instrument_specs: Dict[str, InstrumentSpec] = (
            instrument_specs or {}
        )
        # Build spec lookup from defaults if not provided.
        if not self._instrument_specs:
            self._instrument_specs = {
                s.canonical_symbol: s for s in DEFAULT_INSTRUMENT_SPECS
            }
        # Cache of generated bars: (symbol, timeframe) -> list of OHLCBar
        self._bars_cache: Dict[tuple[str, MarketTimeframe], List[OHLCBar]] = {}

    @property
    def name(self) -> str:
        return f"MockMarketData (Simulated, seed={self._seed})"

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_simulated(self) -> bool:
        return True

    def connect(self) -> bool:
        self._connected = True
        logger.info("Mock market data provider connected (simulated data)")
        return True

    def disconnect(self) -> bool:
        self._connected = False
        logger.info("Mock market data provider disconnected")
        return True

    def get_symbols(self) -> List[MarketSymbol]:
        specs = list(self._instrument_specs.values())
        return [
            MarketSymbol(
                symbol=s.canonical_symbol,
                name=s.name,
                instrument_type=s.instrument_type,
                base_currency=s.base_currency,
                quote_currency=s.quote_currency,
            )
            for s in specs
        ]

    def get_timeframes(self) -> List[MarketTimeframe]:
        return list(MarketTimeframe)

    def spec_for_symbol(self, symbol: str) -> Optional[InstrumentSpec]:
        """Return the InstrumentSpec for a symbol, or None."""
        return self._instrument_specs.get(symbol)

    def _generate_bars(
        self,
        symbol: str,
        timeframe: MarketTimeframe,
        start_time: datetime,
        end_time: datetime,
    ) -> List[OHLCBar]:
        """Generate a sequence of simulated OHLC bars between start and end."""
        key = (symbol, timeframe)
        if key in self._bars_cache:
            cached = self._bars_cache[key]
            return [
                b for b in cached if start_time <= b.timestamp <= end_time
            ]

        spec = self.spec_for_symbol(symbol)
        base_price = self._base_prices.get(symbol, Decimal("1.0"))
        minutes = timeframe.minutes
        step_delta = timedelta(minutes=minutes)

        # Normalize start to the timeframe boundary.
        ts = start_time.replace(second=0, microsecond=0)
        offset_minutes = ts.hour * 60 + ts.minute
        remainder = offset_minutes % minutes
        if remainder != 0:
            ts = ts - timedelta(minutes=remainder)

        bars: List[OHLCBar] = []
        price = base_price
        max_bars = int((end_time - start_time).total_seconds() / 60 / minutes) + 2

        for _ in range(max_bars):
            if ts > end_time:
                break

            # Geometric random walk.
            change = Decimal(
                str(self._rng.uniform(-float(self._volatility), float(self._volatility)))
            )
            open_price = price
            close_price = price * (1 + change)
            close_price = max(close_price, Decimal("0.0001"))

            # High/low derived from open/close plus a small random wick.
            wick = Decimal(
                str(self._rng.uniform(0, float(self._volatility) * 2))
            )
            high_price = max(open_price, close_price) * (1 + wick)
            low_price = min(open_price, close_price) * (1 - wick)
            low_price = max(low_price, Decimal("0.0001"))

            tick_vol = self._rng.randint(10, 1000)
            real_vol = self._rng.randint(100, 10000)
            spread = Decimal(
                str(self._rng.uniform(0.0001, 0.005))
            )

            # Apply instrument spec precision if available.
            if spec is not None and spec.price_precision is not None:
                q = Decimal(1).scaleb(-spec.price_precision)
                open_price = open_price.quantize(q)
                high_price = high_price.quantize(q)
                low_price = low_price.quantize(q)
                close_price = close_price.quantize(q)
                spread = spread.quantize(q)

            bar = OHLCBar(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=ts,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                tick_volume=tick_vol,
                real_volume=real_vol,
                spread=spread,
                is_complete=True,
                timestamp_convention="bar_open",
                data_source=DataSource.SIMULATED,
                bid=open_price - spread / 2 if spread else None,
                ask=open_price + spread / 2 if spread else None,
            )
            bars.append(bar)
            price = close_price
            ts += step_delta

        self._bars_cache[key] = bars
        return [b for b in bars if start_time <= b.timestamp <= end_time]

    def get_candles(
        self,
        symbol: str,
        timeframe: MarketTimeframe,
        start_time: datetime,
        end_time: datetime,
    ) -> List[OHLCBar]:
        if not self._connected:
            logger.warning("get_candles called while disconnected")
            return []

        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        if start_time > end_time:
            return []

        return self._generate_bars(symbol, timeframe, start_time, end_time)

    def get_latest_candle(
        self,
        symbol: str,
        timeframe: MarketTimeframe,
    ) -> Optional[OHLCBar]:
        if not self._connected:
            return None
        now = datetime.now(timezone.utc)
        bars = self.get_candles(symbol, timeframe, now - timedelta(days=30), now)
        return bars[-1] if bars else None

    def get_quote(self, symbol: str) -> Optional[MarketQuote]:
        if not self._connected:
            return None
        base = self._base_prices.get(symbol, Decimal("1.0"))
        spec = self.spec_for_symbol(symbol)
        spread_pct = Decimal("0.0002")
        half_spread = base * spread_pct / 2
        bid = base - half_spread
        ask = base + half_spread
        if spec is not None and spec.price_precision is not None:
            q = Decimal(1).scaleb(-spec.price_precision)
            bid = bid.quantize(q)
            ask = ask.quantize(q)
            base = base.quantize(q)
        return MarketQuote(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            bid=bid,
            ask=ask,
            last=base,
            volume=self._rng.randint(1, 100),
        )
