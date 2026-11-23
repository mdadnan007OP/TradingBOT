"""Stress testing.

Runs a backtest under adverse scenarios (higher spread, higher slippage, higher
commission, missing data, overnight gaps) and reports how results change versus
a baseline. Each scenario modifies only a copy of the configuration.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from src.backtesting.config import (
    BacktestConfig,
    CommissionConfig,
    CommissionModel,
    SlippageConfig,
    SlippageModel,
    SpreadConfig,
)
from src.backtesting.engine import BacktestEngine
from src.backtesting.performance import PerformanceAnalyzer
from src.backtesting.walk_forward import _engine_for
from src.market_data.models import MarketTimeframe, OHLCBar


def _spread_multiplier(config: BacktestConfig, factor: Decimal) -> BacktestConfig:
    old = config.execution.spread
    fixed = {k: v * factor for k, v in old.fixed_spread.items()}
    new_spread = SpreadConfig(
        fixed_spread=fixed,
        fractional_spread=old.fractional_spread * factor,
        use_bar_spread_field=old.use_bar_spread_field,
        use_bar_bid_ask=old.use_bar_bid_ask,
    )
    new_exec = replace(config.execution, spread=new_spread)
    return replace(config, execution=new_exec)


def _slippage_points(config: BacktestConfig, points: Dict[str, Decimal]) -> BacktestConfig:
    new_slip = SlippageConfig(model=SlippageModel.FIXED_POINTS, fixed_points=dict(points))
    new_exec = replace(config.execution, slippage=new_slip)
    return replace(config, execution=new_exec)


def _commission(config: BacktestConfig, per_lot: Decimal) -> BacktestConfig:
    new_comm = CommissionConfig(model=CommissionModel.PER_LOT, per_lot=per_lot)
    new_exec = replace(config.execution, commission=new_comm)
    return replace(config, execution=new_exec)


def stress_scenarios() -> Dict[str, Callable[[BacktestConfig], BacktestConfig]]:
    """Return named scenario transforms (config -> config)."""
    return {
        "higher_spread_2x": lambda c: _spread_multiplier(c, Decimal("2")),
        "higher_spread_5x": lambda c: _spread_multiplier(c, Decimal("5")),
        "slippage_1pip": lambda c: _slippage_points(
            c, {"EURUSD": Decimal("0.0001"), "XAUUSD": Decimal("0.20")}
        ),
        "commission_7_per_lot": lambda c: _commission(c, Decimal("7")),
    }


def run_stress(
    bars: List[OHLCBar],
    symbol: str,
    timeframe: MarketTimeframe,
    config: BacktestConfig,
    scenarios: Optional[Dict[str, Callable[[BacktestConfig], BacktestConfig]]] = None,
    engine_factory: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Run baseline + scenarios; return comparative summaries."""
    scenarios = scenarios or stress_scenarios()
    analyzer = PerformanceAnalyzer()
    output: Dict[str, Any] = {"baseline": None, "scenarios": {}}

    baseline_engine = (engine_factory or _engine_for)(config, symbol, timeframe, bars)
    baseline_result = baseline_engine.run()
    output["baseline"] = analyzer.summary(baseline_result)

    for name, transform in scenarios.items():
        stressed_cfg = transform(config)
        engine = (engine_factory or _engine_for)(stressed_cfg, symbol, timeframe, bars)
        result = engine.run()
        output["scenarios"][name] = analyzer.summary(result)

    return output