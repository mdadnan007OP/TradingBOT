"""Phase 8 backtesting tests — shared fixtures and helpers.

Deterministic synthetic candles and a scripted strategy let the tests drive the
engine through precise entry/exit scenarios without relying on broker data.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional

import pytest

from src.backtesting.config import (
    AccountConfig,
    AmbiguousFillPolicy,
    BacktestConfig,
    CommissionConfig,
    CommissionModel,
    ExecutionConfig,
    SlippageConfig,
    SlippageModel,
    SpreadConfig,
    SwapConfig,
    test_backtest_config,
)
from src.indicators.base import IndicatorParameters
from src.market_data.models import DataSource, MarketTimeframe, OHLCBar
from src.strategies.base import (
    MarketRegime,
    Signal,
    SignalDirection,
    SignalStatus,
    Strategy,
    StrategyResult,
)


def relaxed_risk_policy():
    """A risk policy relaxed enough to let 1%-risk sizing produce trades.

    The Phase 6 default test policy caps per-instrument exposure at 20% of
    equity, which (mathematically) blocks 1%-risk / 0.5%-stop sizing. Engine
    tests use this relaxed policy so simulated trades are actually approved.
    """
    import dataclasses
    from src.risk_management.config import test_policy

    base = test_policy()
    return dataclasses.replace(
        base,
        max_exposure_per_instrument_percent=Decimal("10"),
        max_exposure_per_asset_class_percent=Decimal("10"),
        max_margin_usage_percent=Decimal("0.90"),
        max_stop_distance=None,
        max_stop_distance_percent=None,
    )

BASE = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Candle builders
# ---------------------------------------------------------------------------

def make_bars(
    closes: List[float],
    symbol: str = "EURUSD",
    timeframe: MarketTimeframe = MarketTimeframe.H1,
    start: datetime = BASE,
    spread: Optional[float] = None,
) -> List[OHLCBar]:
    """Build OHLC bars from a close-price path.

    open = previous close (first open = first close), high/low = max/min of
    open/close +/- a small wick.
    """
    bars: List[OHLCBar] = []
    prev_close: Optional[float] = None
    for i, close in enumerate(closes):
        open_ = prev_close if prev_close is not None else close
        high = max(open_, close) + 0.0005
        low = min(open_, close) - 0.0005
        bars.append(
            OHLCBar(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=start + timedelta(hours=i),
                open=Decimal(str(open_)),
                high=Decimal(str(high)),
                low=Decimal(str(low)),
                close=Decimal(str(close)),
                tick_volume=100,
                spread=Decimal(str(spread)) if spread is not None else None,
                data_source=DataSource.HISTORICAL,
            )
        )
        prev_close = close
    return bars


def make_bar(
    symbol: str,
    timeframe: MarketTimeframe,
    timestamp: datetime,
    open_: float,
    high: float,
    low: float,
    close: float,
    is_complete: bool = True,
    data_source: DataSource = DataSource.HISTORICAL,
) -> OHLCBar:
    return OHLCBar(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        is_complete=is_complete,
        data_source=data_source,
    )


def make_signal(
    symbol: str = "EURUSD",
    direction: SignalDirection = SignalDirection.LONG,
    reference_price: Optional[Decimal] = None,
    technical_invalidation: Optional[Decimal] = None,
    market_data_timestamp: datetime = BASE,
    signal_id: str = "sig-1",
    strategy_name: str = "Scripted",
    atr: Optional[Decimal] = None,
) -> Signal:
    snapshot: Dict[str, List[Optional[Decimal]]] = {}
    if atr is not None:
        snapshot["atr"] = [atr]
    return Signal(
        signal_id=signal_id,
        strategy_name=strategy_name,
        strategy_version="1.0",
        symbol=symbol,
        instrument_type="forex",
        direction=direction,
        status=SignalStatus.ACTIVE,
        entry_timeframe=MarketTimeframe.H1,
        confirmation_timeframes=[],
        signal_timestamp=market_data_timestamp,
        market_data_timestamp=market_data_timestamp,
        reference_price=reference_price,
        technical_invalidation=technical_invalidation,
        parameters=IndicatorParameters(values={}),
        indicator_snapshot=snapshot,
        market_regime=MarketRegime.TRENDING,
        confirmation_conditions=[],
        explanation="scripted",
        expiry_conditions=[],
        data_source=DataSource.HISTORICAL,
        strategy_validity_state="valid",
        signal_valid_until=None,
    )


# ---------------------------------------------------------------------------
# Scripted strategy
# ---------------------------------------------------------------------------

class ScriptedStrategy(Strategy):
    """Emits a pre-programmed signal at a given bar index (for engine tests).

    ``signals_by_index`` maps the *absolute* bar index (position in the revealed
    series) to a SignalDirection. A direction of NONE (or a missing index)
    produces no signal.
    """

    def __init__(self, signals_by_index: Dict[int, SignalDirection], name: str = "Scripted") -> None:
        self._signals_by_index = dict(signals_by_index)
        self._enabled = True
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def required_timeframes(self) -> List[MarketTimeframe]:
        return [MarketTimeframe.H1]

    @property
    def supported_instruments(self):
        return None

    @property
    def supported_regimes(self) -> List[MarketRegime]:
        return list(MarketRegime)

    @property
    def default_parameters(self) -> IndicatorParameters:
        return IndicatorParameters(values={})

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        return parameters

    def analyze(self, symbol, candles_by_timeframe, indicator_engine, parameters=None, data_source=DataSource.SIMULATED) -> StrategyResult:
        candles = candles_by_timeframe.get(MarketTimeframe.H1, [])
        entry_tf = MarketTimeframe.H1
        if not candles:
            return StrategyResult(
                strategy_name=self.name, symbol=symbol, timeframe=entry_tf,
                signals=[], rejections=[], market_regime=MarketRegime.UNKNOWN,
                indicator_snapshots={},
            )
        idx = len(candles) - 1
        direction = self._signals_by_index.get(idx, SignalDirection.NONE)
        if direction == SignalDirection.NONE:
            return StrategyResult(
                strategy_name=self.name, symbol=symbol, timeframe=entry_tf,
                signals=[], rejections=[], market_regime=MarketRegime.TRENDING,
                indicator_snapshots={},
            )
        last = candles[-1]
        sig = make_signal(
            symbol=symbol,
            direction=direction,
            reference_price=last.close,
            technical_invalidation=None,
            market_data_timestamp=last.timestamp,
            signal_id=f"scripted-{symbol}-{idx}",
            strategy_name=self.name,
        )
        return StrategyResult(
            strategy_name=self.name, symbol=symbol, timeframe=entry_tf,
            signals=[sig], rejections=[], market_regime=MarketRegime.TRENDING,
            indicator_snapshots={},
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_time():
    return BASE


@pytest.fixture
def config():
    return test_backtest_config()


@pytest.fixture
def account_config():
    return AccountConfig(starting_balance=Decimal("10000"), currency="USD", leverage=Decimal("30"))