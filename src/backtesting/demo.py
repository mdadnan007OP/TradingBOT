"""Reproducible backtesting demonstration.

Runs a self-contained, deterministic backtest on synthetic historical data for
EURUSD (forex) and XAUUSD (gold) so the engine can be exercised without any
network, MT5 terminal, or broker credentials. A small SMA-crossover momentum
strategy (reusing the Phase 4 indicator engine) produces signals, which are then
passed through the Phase 6 risk engine and simulated execution.

Results are simulated historical backtest results — not guarantees of future
performance.

Run:
    python -m src.backtesting.demo
"""

from __future__ import annotations

import dataclasses
import math
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List

from src.backtesting.config import AccountConfig, test_backtest_config
from src.backtesting.data_loader import BacktestDataLoader
from src.backtesting.engine import BacktestEngine
from src.backtesting.performance import PerformanceAnalyzer
from src.backtesting.reporting import format_summary, write_all
from src.indicators import create_engine
from src.indicators.base import IndicatorParameters
from src.market_data.models import DataSource, MarketTimeframe, OHLCBar
from src.risk_management.config import test_policy
from src.strategies.base import (
    MarketRegime,
    Signal,
    SignalDirection,
    SignalStatus,
    Strategy,
    StrategyResult,
)
from src.strategies.manager import StrategyManager
from src.strategies.registry import StrategyRegistry

START = datetime(2025, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Reproducible synthetic data
# ---------------------------------------------------------------------------

def _synthetic_series(
    symbol: str,
    base: float,
    n: int,
    timeframe: MarketTimeframe,
    seed: int,
    drift: float = 0.0,
    wave: float = 0.0,
) -> List[OHLCBar]:
    """Deterministic pseudo-random OHLC series (no external RNG)."""
    bars: List[OHLCBar] = []
    price = base
    for i in range(n):
        cycle = math.sin((i + seed) / 7.0) * wave
        noise = math.sin((i * (seed + 3)) / 3.0) * (base * 0.0008)
        close = base + drift * i + cycle + noise
        open_ = price
        high = max(open_, close) + base * 0.0006
        low = min(open_, close) - base * 0.0006
        bars.append(OHLCBar(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=START + timedelta(minutes=timeframe.minutes) * i,
            open=Decimal(str(round(open_, 5))),
            high=Decimal(str(round(high, 5))),
            low=Decimal(str(round(low, 5))),
            close=Decimal(str(round(close, 5))),
            tick_volume=100,
            data_source=DataSource.HISTORICAL,
        ))
        price = close
    return bars


# ---------------------------------------------------------------------------
# Simple SMA-crossover momentum strategy (demo only)
# ---------------------------------------------------------------------------

class MomentumStrategy(Strategy):
    """LONG on fast SMA crossing above slow SMA; SHORT on the opposite cross."""

    def __init__(self, fast: int = 10, slow: int = 30) -> None:
        self._fast = fast
        self._slow = slow

    @property
    def name(self) -> str:
        return "DemoMomentum"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def enabled(self) -> bool:
        return True

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
        return IndicatorParameters(values={"fast": self._fast, "slow": self._slow})

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        return parameters

    def analyze(self, symbol, candles_by_timeframe, indicator_engine, parameters=None, data_source=DataSource.SIMULATED) -> StrategyResult:
        candles = candles_by_timeframe.get(MarketTimeframe.H1, [])
        entry_tf = MarketTimeframe.H1
        if len(candles) < self._slow + 2:
            return StrategyResult(
                strategy_name=self.name, symbol=symbol, timeframe=entry_tf,
                signals=[], rejections=[], market_regime=MarketRegime.UNKNOWN,
                indicator_snapshots={},
            )
        params = IndicatorParameters(values={"periods": [self._fast, self._slow]})
        result = indicator_engine.calculate("SMA", symbol, entry_tf, candles, params, data_source)
        fast_key = f"sma_{self._fast}"
        slow_key = f"sma_{self._slow}"
        fast = result.values.get(fast_key, [])
        slow = result.values.get(slow_key, [])
        if len(fast) < 2 or len(slow) < 2:
            return StrategyResult(
                strategy_name=self.name, symbol=symbol, timeframe=entry_tf,
                signals=[], rejections=[], market_regime=MarketRegime.TRENDING,
                indicator_snapshots={},
            )
        last = candles[-1]
        direction = SignalDirection.NONE
        if fast[-1] is not None and slow[-1] is not None and fast[-2] is not None and slow[-2] is not None:
            if fast[-2] <= slow[-2] and fast[-1] > slow[-1]:
                direction = SignalDirection.LONG
            elif fast[-2] >= slow[-2] and fast[-1] < slow[-1]:
                direction = SignalDirection.SHORT
        if direction == SignalDirection.NONE:
            return StrategyResult(
                strategy_name=self.name, symbol=symbol, timeframe=entry_tf,
                signals=[], rejections=[], market_regime=MarketRegime.TRENDING,
                indicator_snapshots={},
            )
        sig = Signal(
            signal_id=f"momentum-{symbol}-{last.timestamp.isoformat()}",
            strategy_name=self.name,
            strategy_version=self.version,
            symbol=symbol,
            instrument_type="forex",
            direction=direction,
            status=SignalStatus.ACTIVE,
            entry_timeframe=entry_tf,
            confirmation_timeframes=[],
            signal_timestamp=last.timestamp,
            market_data_timestamp=last.timestamp,
            reference_price=last.close,
            technical_invalidation=None,
            parameters=params,
            indicator_snapshot={},
            market_regime=MarketRegime.TRENDING,
            confirmation_conditions=[],
            explanation="SMA crossover",
            expiry_conditions=[],
            data_source=data_source,
            strategy_validity_state="valid",
            signal_valid_until=None,
        )
        return StrategyResult(
            strategy_name=self.name, symbol=symbol, timeframe=entry_tf,
            signals=[sig], rejections=[], market_regime=MarketRegime.TRENDING,
            indicator_snapshots={},
        )


# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------

def _demo_policy():
    """Relaxed policy so 1%-risk sizing produces trades in the demo."""
    base = test_policy()
    return dataclasses.replace(
        base,
        max_exposure_per_instrument_percent=Decimal("10"),
        max_exposure_per_asset_class_percent=Decimal("10"),
        max_margin_usage_percent=Decimal("0.90"),
        max_stop_distance=None,
        max_stop_distance_percent=None,
    )


def _run_one(symbol: str, bars: List[OHLCBar], name: str, output_dir: str, analyzer: PerformanceAnalyzer):
    data = BacktestDataLoader().from_lists({(symbol, bars[0].timeframe): bars})
    registry = StrategyRegistry()
    registry.register(MomentumStrategy())
    manager = StrategyManager(indicator_engine=create_engine(), registry=registry)
    cfg = test_backtest_config(overrides={
        "name": name,
        "account": AccountConfig(starting_balance=Decimal("100000"), currency="USD", leverage=Decimal("30")),
        "symbols": [symbol],
        "timeframes": ["H1"],
        "strategies": ["DemoMomentum"],
        "risk_policy": _demo_policy(),
    })
    engine = BacktestEngine(cfg, data, strategy_manager=manager)
    result = engine.run()
    summary = analyzer.summary(result)
    write_all(result, output_dir)
    print(format_summary(result))
    print()
    return summary


def run_demo(output_dir: str = "backtest_output") -> Dict[str, dict]:
    """Run reproducible EURUSD and XAUUSD backtests; write reports."""
    analyzer = PerformanceAnalyzer()
    results: Dict[str, dict] = {}

    eurusd_bars = _synthetic_series("EURUSD", 1.1000, 500, MarketTimeframe.H1, seed=1, drift=0.00002, wave=0.0025)
    results["EURUSD"] = _run_one("EURUSD", eurusd_bars, "demo-eurusd", output_dir, analyzer)

    xau_bars = _synthetic_series("XAUUSD", 2000.0, 500, MarketTimeframe.H1, seed=7, drift=0.05, wave=2.0)
    results["XAUUSD"] = _run_one("XAUUSD", xau_bars, "demo-xauusd", output_dir, analyzer)

    print(f"Reports written to: {os.path.abspath(output_dir)}")
    return results


if __name__ == "__main__":
    run_demo()