"""Backtesting configuration.

All configuration is explicit and conservative. Missing/uncertain assumptions
default to *adverse* values (never zero spread, never free fills) and are
documented in the resulting report.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields as dataclasses_fields
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional


class AmbiguousFillPolicy(str, Enum):
    """How to resolve same-candle stop-loss / take-profit ambiguity."""

    CONSERVATIVE = "CONSERVATIVE"
    """Assume the adverse outcome (stop-loss) triggers first."""
    OPTIMISTIC = "OPTIMISTIC"
    """Assume the favourable outcome (take-profit) triggers first (NOT recommended)."""
    SKIP = "SKIP"
    """Do not fill; mark the bar ambiguous and skip the exit."""


class SlippageModel(str, Enum):
    FIXED_POINTS = "FIXED_POINTS"
    FRACTION = "FRACTION"
    NONE = "NONE"


class CommissionModel(str, Enum):
    PER_LOT = "PER_LOT"
    PER_TRADE = "PER_TRADE"
    NONE = "NONE"


@dataclass(frozen=True)
class AccountConfig:
    """Simulated account configuration."""

    starting_balance: Decimal = Decimal("10000")
    currency: str = "USD"
    leverage: Decimal = Decimal("30")
    position_mode: str = "hedging"
    """'hedging' (multiple positions per symbol) or 'netting' (one net position)."""


@dataclass(frozen=True)
class SpreadConfig:
    """Spread assumptions when historical bid/ask is unavailable."""

    # Fixed spread in price units per instrument (adverse fallback).
    fixed_spread: Dict[str, Decimal] = field(default_factory=dict)
    # Fraction-of-price fallback (e.g. 0.0001 = 1 bp).
    fractional_spread: Decimal = Decimal("0.0")
    use_bar_spread_field: bool = True
    use_bar_bid_ask: bool = True


@dataclass(frozen=True)
class SlippageConfig:
    """Slippage assumptions (adverse by default)."""

    model: SlippageModel = SlippageModel.FIXED_POINTS
    fixed_points: Dict[str, Decimal] = field(default_factory=dict)
    """Adverse slippage in price units per instrument."""
    fraction: Decimal = Decimal("0.0")
    """Fraction of price (used when model == FRACTION)."""


@dataclass(frozen=True)
class CommissionConfig:
    """Commission assumptions."""

    model: CommissionModel = CommissionModel.NONE
    per_lot: Decimal = Decimal("0")
    """Commission per lot, in account currency."""
    per_trade: Decimal = Decimal("0")
    """Commission per trade (entry+exit combined), in account currency."""


@dataclass(frozen=True)
class SwapConfig:
    """Overnight financing (swap) assumptions."""

    enabled: bool = False
    long_points: Dict[str, Decimal] = field(default_factory=dict)
    short_points: Dict[str, Decimal] = field(default_factory=dict)
    """Swap in price units per lot per night."""
    triple_days: List[int] = field(default_factory=lambda: [2])  # Wednesday (0=Mon)
    point_value: Dict[str, Decimal] = field(default_factory=dict)
    """Value of 1 price point per lot in account currency (for conversion)."""


@dataclass(frozen=True)
class ExecutionConfig:
    """Execution simulation assumptions."""

    ambiguous_fill_policy: AmbiguousFillPolicy = AmbiguousFillPolicy.CONSERVATIVE
    fill_on_next_bar: bool = True
    """Enter on the next bar after a signal (never at the signal bar close)."""
    allow_partial_fills: bool = False
    pending_order_expiry_bars: int = 0
    """0 = no expiry."""
    slippage: SlippageConfig = field(default_factory=SlippageConfig)
    commission: CommissionConfig = field(default_factory=CommissionConfig)
    swap: SwapConfig = field(default_factory=SwapConfig)
    spread: SpreadConfig = field(default_factory=SpreadConfig)


@dataclass(frozen=True)
class DataConfig:
    """Historical data loading configuration."""

    validate_timestamps: bool = True
    validate_ohlc: bool = True
    drop_duplicate_timestamps: bool = True
    allow_missing_candles: bool = True
    """Missing candles are recorded, never fabricated."""


@dataclass(frozen=True)
class BacktestConfig:
    """Complete backtest configuration."""

    name: str = "backtest"
    account: AccountConfig = field(default_factory=AccountConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    data: DataConfig = field(default_factory=DataConfig)
    symbols: List[str] = field(default_factory=lambda: ["EURUSD"])
    timeframes: List[str] = field(default_factory=lambda: ["H1"])
    strategies: List[str] = field(default_factory=list)
    """Strategy names to run (empty = all registered)."""
    strategy_parameters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    """Per-strategy parameter overrides."""
    warmup_bars: int = 200
    """Bars of history supplied to indicators before the tradable region."""
    fallback_stop_fraction: Decimal = Decimal("0.005")
    """Fallback stop distance as a fraction of price when no ATR/invalidation."""
    starting_equity_override: Optional[Decimal] = None
    news_enabled: bool = False
    """Apply Phase 7 news restrictions (only if historical data provided)."""
    currency_rates: Dict[str, Decimal] = field(default_factory=dict)
    """profit_currency -> account_currency conversion rates (static fallback)."""
    risk_policy: Optional[Any] = None
    """A RiskPolicy instance. If None, a default test policy is used."""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "account": {
                "starting_balance": str(self.account.starting_balance),
                "currency": self.account.currency,
                "leverage": str(self.account.leverage),
                "position_mode": self.account.position_mode,
            },
            "execution": {
                "ambiguous_fill_policy": self.execution.ambiguous_fill_policy.value,
                "fill_on_next_bar": self.execution.fill_on_next_bar,
                "commission_model": self.execution.commission.model.value,
                "slippage_model": self.execution.slippage.model.value,
                "swap_enabled": self.execution.swap.enabled,
            },
            "symbols": self.symbols,
            "timeframes": self.timeframes,
            "strategies": self.strategies,
            "warmup_bars": self.warmup_bars,
            "news_enabled": self.news_enabled,
        }


def test_backtest_config(overrides: Optional[Dict[str, object]] = None) -> BacktestConfig:
    """Deterministic configuration for automated tests."""
    base = BacktestConfig(
        name="test-backtest",
        account=AccountConfig(
            starting_balance=Decimal("10000"),
            currency="USD",
            leverage=Decimal("30"),
        ),
        execution=ExecutionConfig(
            ambiguous_fill_policy=AmbiguousFillPolicy.CONSERVATIVE,
            fill_on_next_bar=True,
            commission=CommissionConfig(model=CommissionModel.NONE),
            slippage=SlippageConfig(model=SlippageModel.NONE),
            swap=SwapConfig(enabled=False),
            spread=SpreadConfig(
                fixed_spread={"EURUSD": Decimal("0.0001"), "XAUUSD": Decimal("0.20")},
                fractional_spread=Decimal("0.0"),
            ),
        ),
        symbols=["EURUSD"],
        timeframes=["H1"],
        strategies=[],
        warmup_bars=50,
        news_enabled=False,
    )
    if not overrides:
        return base
    allowed = {f.name for f in dataclasses_fields(BacktestConfig)}
    applied: Dict[str, object] = {
        f.name: getattr(base, f.name) for f in dataclasses_fields(BacktestConfig)
    }
    for key, value in overrides.items():
        if key not in allowed:
            raise ValueError(f"Unknown backtest config field: {key}")
        applied[key] = value
    return BacktestConfig(**applied)


def default_backtest_config() -> BacktestConfig:
    """A sensible default configuration (conservative, no swaps/commissions).

    Broker-specific commission, swap and financing MUST be configured explicitly
    before drawing real conclusions; these defaults are illustrative only.
    """
    return BacktestConfig(
        name="default",
        account=AccountConfig(
            starting_balance=Decimal("10000"),
            currency="USD",
            leverage=Decimal("30"),
        ),
        execution=ExecutionConfig(
            ambiguous_fill_policy=AmbiguousFillPolicy.CONSERVATIVE,
            fill_on_next_bar=True,
            commission=CommissionConfig(model=CommissionModel.NONE),
            slippage=SlippageConfig(model=SlippageModel.NONE),
            swap=SwapConfig(enabled=False),
            spread=SpreadConfig(
                fixed_spread={
                    "EURUSD": Decimal("0.0001"),
                    "GBPUSD": Decimal("0.00012"),
                    "USDJPY": Decimal("0.012"),
                    "XAUUSD": Decimal("0.20"),
                    "XAGUSD": Decimal("0.02"),
                },
                fractional_spread=Decimal("0.0"),
            ),
        ),
        symbols=["EURUSD"],
        timeframes=["H1"],
        warmup_bars=200,
        news_enabled=False,
    )