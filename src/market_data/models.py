"""Market data models for the Forex trading bot.

All models are immutable frozen dataclasses. They are broker-agnostic: they
describe concepts (symbol, timeframe, OHLC bar, quote, quality report) rather
than any specific broker's API shape.

All internal timestamps are standardized to timezone-aware UTC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import List, Optional


class MarketTimeframe(str, Enum):
    """Supported candlestick timeframes.

    ``minutes`` gives the number of minutes per bar. ``D1`` is 1440 minutes,
    ``W1`` is 10080 minutes (7 days), and ``MN1`` is 43200 minutes (30 days,
    approximate).
    """

    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"
    MN1 = "MN1"

    @property
    def minutes(self) -> int:
        """Return the timeframe length in minutes."""
        mapping = {
            MarketTimeframe.M1: 1,
            MarketTimeframe.M5: 5,
            MarketTimeframe.M15: 15,
            MarketTimeframe.M30: 30,
            MarketTimeframe.H1: 60,
            MarketTimeframe.H4: 240,
            MarketTimeframe.D1: 1440,
            MarketTimeframe.W1: 10080,
            MarketTimeframe.MN1: 43200,
        }
        return mapping[self]

    @classmethod
    def from_string(cls, value: str) -> "MarketTimeframe":
        """Parse a timeframe string, raising ValueError for unknown values."""
        try:
            return cls(value.upper())
        except ValueError as exc:
            raise ValueError(
                f"Unsupported timeframe: {value}. "
                f"Supported: {[t.value for t in cls]}"
            ) from exc


class InstrumentType(str, Enum):
    FOREX = "forex"
    METAL = "metal"
    ENERGY = "energy"
    INDEX = "index"
    EQUITY = "equity"
    CRYPTO = "crypto"
    OTHER = "other"


class CandleCompletion(str, Enum):
    """Whether a candle represents a completed bar or an incomplete/partial bar."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class DataSource(str, Enum):
    """Classification of where market data originated."""

    SIMULATED = "simulated"
    HISTORICAL = "historical"
    LIVE = "live"


class VolumeType(str, Enum):
    """Type of volume reported for an instrument."""

    TICK = "tick"
    REAL = "real"
    BOTH = "both"
    NONE = "none"


@dataclass(frozen=True)
class InstrumentSpec:
    """Configurable specification for a financial instrument.

    Attributes that are not yet known remain optional and are deliberately NOT
    invented. Broker-specific specifications will be verified during Phase 3.

    Attributes:
        canonical_symbol: Internal canonical symbol (e.g. ``XAUUSD``).
        broker_symbol: Broker-specific symbol string, if different from canonical.
        name: Human-readable name.
        instrument_type: Asset class (forex, metal, energy, index, etc.).
        base_currency: Base currency for pairs (None for non-pairs).
        quote_currency: Quote currency for pairs (None for non-pairs).
        price_precision: Number of decimal places for price display.
        tick_size: Minimum price increment (tick size).
        pip_size: Pip size, where applicable (None for non-forex-style).
        contract_size: Contract size per lot, where known.
        volume_type: Type of volume reported (tick, real, both, none).
        supported_timeframes: Timeframes supported for this instrument.
        market_session: Market session identifier, if applicable.
    """

    canonical_symbol: str
    broker_symbol: Optional[str] = None
    name: str = ""
    instrument_type: InstrumentType = InstrumentType.FOREX
    base_currency: Optional[str] = None
    quote_currency: Optional[str] = None
    price_precision: Optional[int] = None
    tick_size: Optional[Decimal] = None
    pip_size: Optional[Decimal] = None
    contract_size: Optional[Decimal] = None
    volume_type: VolumeType = VolumeType.NONE
    supported_timeframes: Optional[List[MarketTimeframe]] = None
    market_session: Optional[str] = None

    def __post_init__(self) -> None:
        if self.supported_timeframes is None:
            object.__setattr__(
                self, "supported_timeframes", list(MarketTimeframe)
            )


@dataclass(frozen=True)
class MarketSymbol:
    """A tradable financial instrument identifier.

    Attributes:
        symbol: Trading symbol string (e.g. ``XAUUSD``).
        name: Human-readable name.
        instrument_type: Category (forex, metal, etc.).
        base_currency: Base currency for pairs (None for metals).
        quote_currency: Quote currency for pairs (None for metals).
    """

    symbol: str
    name: str
    instrument_type: InstrumentType = InstrumentType.FOREX
    base_currency: Optional[str] = None
    quote_currency: Optional[str] = None


# Default configured symbol universe. Broker-specific contract sizes and
# decimal precision must be discovered during future broker integration; they
# are deliberately NOT assumed here.
DEFAULT_SYMBOLS: List[MarketSymbol] = [
    MarketSymbol(symbol="XAUUSD", name="Gold vs US Dollar", instrument_type=InstrumentType.METAL, base_currency="XAU", quote_currency="USD"),
    MarketSymbol(symbol="XAGUSD", name="Silver vs US Dollar", instrument_type=InstrumentType.METAL, base_currency="XAG", quote_currency="USD"),
    MarketSymbol(symbol="EURUSD", name="Euro vs US Dollar", instrument_type=InstrumentType.FOREX, base_currency="EUR", quote_currency="USD"),
    MarketSymbol(symbol="GBPUSD", name="Great Britain Pound vs US Dollar", instrument_type=InstrumentType.FOREX, base_currency="GBP", quote_currency="USD"),
    MarketSymbol(symbol="USDJPY", name="US Dollar vs Japanese Yen", instrument_type=InstrumentType.FOREX, base_currency="USD", quote_currency="JPY"),
    MarketSymbol(symbol="AUDUSD", name="Australian Dollar vs US Dollar", instrument_type=InstrumentType.FOREX, base_currency="AUD", quote_currency="USD"),
    MarketSymbol(symbol="USDCAD", name="US Dollar vs Canadian Dollar", instrument_type=InstrumentType.FOREX, base_currency="USD", quote_currency="CAD"),
]

# Extended default instrument specifications covering multiple asset classes.
# Broker-specific values (contract sizes, pip sizes, etc.) are NOT assumed and
# remain None until verified in Phase 3.
DEFAULT_INSTRUMENT_SPECS: List[InstrumentSpec] = [
    # Forex
    InstrumentSpec(
        canonical_symbol="EURUSD",
        name="Euro vs US Dollar",
        instrument_type=InstrumentType.FOREX,
        base_currency="EUR",
        quote_currency="USD",
        price_precision=5,
        tick_size=Decimal("0.00001"),
        pip_size=Decimal("0.0001"),
        contract_size=Decimal("100000"),
        volume_type=VolumeType.TICK,
        market_session="forex",
    ),
    InstrumentSpec(
        canonical_symbol="GBPUSD",
        name="Great Britain Pound vs US Dollar",
        instrument_type=InstrumentType.FOREX,
        base_currency="GBP",
        quote_currency="USD",
        price_precision=5,
        tick_size=Decimal("0.00001"),
        pip_size=Decimal("0.0001"),
        contract_size=Decimal("100000"),
        volume_type=VolumeType.TICK,
        market_session="forex",
    ),
    InstrumentSpec(
        canonical_symbol="USDJPY",
        name="US Dollar vs Japanese Yen",
        instrument_type=InstrumentType.FOREX,
        base_currency="USD",
        quote_currency="JPY",
        price_precision=3,
        tick_size=Decimal("0.001"),
        pip_size=Decimal("0.01"),
        contract_size=Decimal("100000"),
        volume_type=VolumeType.TICK,
        market_session="forex",
    ),
    InstrumentSpec(
        canonical_symbol="AUDUSD",
        name="Australian Dollar vs US Dollar",
        instrument_type=InstrumentType.FOREX,
        base_currency="AUD",
        quote_currency="USD",
        price_precision=5,
        tick_size=Decimal("0.00001"),
        pip_size=Decimal("0.0001"),
        contract_size=Decimal("100000"),
        volume_type=VolumeType.TICK,
        market_session="forex",
    ),
    InstrumentSpec(
        canonical_symbol="USDCAD",
        name="US Dollar vs Canadian Dollar",
        instrument_type=InstrumentType.FOREX,
        base_currency="USD",
        quote_currency="CAD",
        price_precision=5,
        tick_size=Decimal("0.00001"),
        pip_size=Decimal("0.0001"),
        contract_size=Decimal("100000"),
        volume_type=VolumeType.TICK,
        market_session="forex",
    ),
    # Precious metals
    InstrumentSpec(
        canonical_symbol="XAUUSD",
        name="Gold vs US Dollar",
        instrument_type=InstrumentType.METAL,
        base_currency="XAU",
        quote_currency="USD",
        price_precision=2,
        tick_size=Decimal("0.01"),
        contract_size=Decimal("100"),
        volume_type=VolumeType.TICK,
        market_session="metals",
    ),
    InstrumentSpec(
        canonical_symbol="XAGUSD",
        name="Silver vs US Dollar",
        instrument_type=InstrumentType.METAL,
        base_currency="XAG",
        quote_currency="USD",
        price_precision=3,
        tick_size=Decimal("0.001"),
        contract_size=Decimal("5000"),
        volume_type=VolumeType.TICK,
        market_session="metals",
    ),
    InstrumentSpec(
        canonical_symbol="XPTUSD",
        name="Platinum vs US Dollar",
        instrument_type=InstrumentType.METAL,
        base_currency="XPT",
        quote_currency="USD",
        price_precision=2,
        tick_size=Decimal("0.01"),
        contract_size=Decimal("100"),
        volume_type=VolumeType.TICK,
        market_session="metals",
    ),
    InstrumentSpec(
        canonical_symbol="XPDUSD",
        name="Palladium vs US Dollar",
        instrument_type=InstrumentType.METAL,
        base_currency="XPD",
        quote_currency="USD",
        price_precision=2,
        tick_size=Decimal("0.01"),
        contract_size=Decimal("100"),
        volume_type=VolumeType.TICK,
        market_session="metals",
    ),
    # Energy
    InstrumentSpec(
        canonical_symbol="WTIUSD",
        name="WTI Crude Oil vs US Dollar",
        instrument_type=InstrumentType.ENERGY,
        base_currency="WTI",
        quote_currency="USD",
        price_precision=3,
        tick_size=Decimal("0.001"),
        contract_size=Decimal("1000"),
        volume_type=VolumeType.REAL,
        market_session="energy",
    ),
    InstrumentSpec(
        canonical_symbol="BRENTUSD",
        name="Brent Crude Oil vs US Dollar",
        instrument_type=InstrumentType.ENERGY,
        base_currency="BRENT",
        quote_currency="USD",
        price_precision=3,
        tick_size=Decimal("0.001"),
        contract_size=Decimal("1000"),
        volume_type=VolumeType.REAL,
        market_session="energy",
    ),
    InstrumentSpec(
        canonical_symbol="NATGASUSD",
        name="Natural Gas vs US Dollar",
        instrument_type=InstrumentType.ENERGY,
        base_currency="NATGAS",
        quote_currency="USD",
        price_precision=3,
        tick_size=Decimal("0.001"),
        contract_size=Decimal("10000"),
        volume_type=VolumeType.REAL,
        market_session="energy",
    ),
    # Indices
    InstrumentSpec(
        canonical_symbol="NAS100",
        name="Nasdaq 100 Index",
        instrument_type=InstrumentType.INDEX,
        price_precision=2,
        tick_size=Decimal("0.01"),
        contract_size=Decimal("20"),
        volume_type=VolumeType.TICK,
        market_session="indices",
    ),
    InstrumentSpec(
        canonical_symbol="US500",
        name="S&P 500 Index",
        instrument_type=InstrumentType.INDEX,
        price_precision=2,
        tick_size=Decimal("0.01"),
        contract_size=Decimal("50"),
        volume_type=VolumeType.TICK,
        market_session="indices",
    ),
    InstrumentSpec(
        canonical_symbol="US30",
        name="Dow Jones 30 Index",
        instrument_type=InstrumentType.INDEX,
        price_precision=2,
        tick_size=Decimal("0.01"),
        contract_size=Decimal("5"),
        volume_type=VolumeType.TICK,
        market_session="indices",
    ),
    InstrumentSpec(
        canonical_symbol="GER40",
        name="DAX 40 Index",
        instrument_type=InstrumentType.INDEX,
        price_precision=2,
        tick_size=Decimal("0.01"),
        contract_size=Decimal("25"),
        volume_type=VolumeType.TICK,
        market_session="indices",
    ),
    InstrumentSpec(
        canonical_symbol="UK100",
        name="FTSE 100 Index",
        instrument_type=InstrumentType.INDEX,
        price_precision=2,
        tick_size=Decimal("0.01"),
        contract_size=Decimal("10"),
        volume_type=VolumeType.TICK,
        market_session="indices",
    ),
    # Cryptocurrencies
    InstrumentSpec(
        canonical_symbol="BTCUSD",
        name="Bitcoin vs US Dollar",
        instrument_type=InstrumentType.CRYPTO,
        base_currency="BTC",
        quote_currency="USD",
        price_precision=2,
        tick_size=Decimal("0.01"),
        contract_size=Decimal("1"),
        volume_type=VolumeType.REAL,
        market_session="crypto",
    ),
    InstrumentSpec(
        canonical_symbol="ETHUSD",
        name="Ethereum vs US Dollar",
        instrument_type=InstrumentType.CRYPTO,
        base_currency="ETH",
        quote_currency="USD",
        price_precision=2,
        tick_size=Decimal("0.01"),
        contract_size=Decimal("1"),
        volume_type=VolumeType.REAL,
        market_session="crypto",
    ),
]


def spec_for_symbol(symbol: str) -> Optional[InstrumentSpec]:
    """Look up an ``InstrumentSpec`` by canonical symbol.

    Returns None if no spec is registered for the symbol.
    """
    for spec in DEFAULT_INSTRUMENT_SPECS:
        if spec.canonical_symbol == symbol:
            return spec
    return None


@dataclass(frozen=True)
class OHLCBar:
    """A single OHLC candlestick bar.

    Attributes:
        symbol: Trading symbol (e.g. ``XAUUSD``).
        timeframe: Candle timeframe (e.g. ``M1``).
        timestamp: Bar open time, timezone-aware UTC.
        open: Opening price.
        high: Highest price.
        low: Lowest price.
        close: Closing price.
        tick_volume: Number of price ticks received (broker-specific concept).
        real_volume: Actual traded volume, if available (broker-specific concept).
        spread: Bid-ask spread at bar open, if available.
        is_complete: Whether the bar is complete (True) or incomplete/partial (False).
        timestamp_convention: Convention used for the timestamp (e.g. ``bar_open``).
        data_source: Classification of data origin (simulated, historical, live).
        bid: Bid price at bar time, if available.
        ask: Ask price at bar time, if available.
    """

    symbol: str
    timeframe: MarketTimeframe
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    tick_volume: Optional[int] = None
    real_volume: Optional[int] = None
    spread: Optional[Decimal] = None
    is_complete: bool = True
    timestamp_convention: str = "bar_open"
    data_source: DataSource = DataSource.SIMULATED
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None

    def __post_init__(self) -> None:
        """Validate OHLC relationships and timestamp."""
        # Ensure timestamp is timezone-aware UTC.
        if self.timestamp.tzinfo is None:
            raise ValueError(
                f"Timestamp for {self.symbol} must be timezone-aware UTC, "
                f"got naive datetime: {self.timestamp}"
            )
        # Prices must be positive.
        for name, value in (("open", self.open), ("high", self.high), ("low", self.low), ("close", self.close)):
            if value <= 0:
                raise ValueError(f"{name} price must be positive for {self.symbol}, got {value}")
        # OHLC relationships.
        if self.high < max(self.open, self.close):
            raise ValueError(
                f"High {self.high} is lower than open/close for {self.symbol}"
            )
        if self.low > min(self.open, self.close):
            raise ValueError(
                f"Low {self.low} is higher than open/close for {self.symbol}"
            )
        if self.high < self.low:
            raise ValueError(
                f"High {self.high} is lower than low {self.low} for {self.symbol}"
            )
        # Volumes/spread must not be negative.
        if self.tick_volume is not None and self.tick_volume < 0:
            raise ValueError(f"tick_volume must not be negative for {self.symbol}")
        if self.real_volume is not None and self.real_volume < 0:
            raise ValueError(f"real_volume must not be negative for {self.symbol}")
        if self.spread is not None and self.spread < 0:
            raise ValueError(f"spread must not be negative for {self.symbol}")
        # Incomplete candles cannot be treated as complete historical bars.
        if self.is_complete is False and self.data_source == DataSource.HISTORICAL:
            raise ValueError(
                f"Historical candle for {self.symbol} at {self.timestamp} "
                f"is marked incomplete; historical bars must be complete."
            )

    @property
    def is_utc(self) -> bool:
        """Return True if timestamp is timezone-aware."""
        return self.timestamp.tzinfo is not None

    @property
    def typical_price(self) -> Decimal:
        """Return the typical price (H+L+C)/3."""
        return (self.high + self.low + self.close) / 3


@dataclass(frozen=True)
class MarketQuote:
    """A real-time bid/ask quote.

    Attributes:
        symbol: Trading symbol.
        timestamp: Quote time, timezone-aware UTC.
        bid: Best bid price.
        ask: Best ask price.
        last: Last traded price, if available.
        volume: Volume at last price, if available.
    """

    symbol: str
    timestamp: datetime
    bid: Decimal
    ask: Decimal
    last: Optional[Decimal] = None
    volume: Optional[int] = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError(
                f"Quote timestamp for {self.symbol} must be timezone-aware UTC"
            )
        if self.bid <= 0 or self.ask <= 0:
            raise ValueError(f"Bid/ask must be positive for {self.symbol}")
        if self.ask < self.bid:
            raise ValueError(f"Ask {self.ask} below bid {self.bid} for {self.symbol}")

    @property
    def spread(self) -> Decimal:
        """Bid-ask spread."""
        return self.ask - self.bid

    @property
    def mid(self) -> Decimal:
        """Mid price."""
        return (self.bid + self.ask) / 2


@dataclass(frozen=True)
class ValidationIssue:
    """A single validation finding.

    Attributes:
        severity: ``error`` or ``warning``.
        code: Machine-readable issue code.
        message: Human-readable description.
        timestamp: Optional timestamp the issue relates to.
    """

    severity: str
    code: str
    message: str
    timestamp: Optional[datetime] = None


@dataclass(frozen=True)
class DataQualityReport:
    """Validation report for a set of candles.

    Attributes:
        symbol: Symbol that was validated.
        timeframe: Timeframe that was validated.
        total_candles: Total number of candles examined.
        valid_candles: Number of candles that passed all checks.
        invalid_candles: Number of candles that failed at least one check.
        issues: List of validation findings.
        missing_intervals: List of expected-but-missing timestamps.
        is_valid: True if no error-severity issues were found.
        session_aware: True if market session awareness was applied.
    """

    symbol: str
    timeframe: MarketTimeframe
    total_candles: int
    valid_candles: int
    invalid_candles: int
    issues: List[ValidationIssue] = field(default_factory=list)
    missing_intervals: List[datetime] = field(default_factory=list)
    session_aware: bool = False

    @property
    def is_valid(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")
