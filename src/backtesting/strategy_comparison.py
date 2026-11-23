"""Strategy comparison.

Runs the same historical data through individual strategies (and a combined
portfolio) so configurations can be compared fairly. Original strategy
parameters are never silently changed; overrides are explicit per run.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List

from src.backtesting.config import BacktestConfig
from src.backtesting.engine import BacktestEngine
from src.backtesting.performance import PerformanceAnalyzer
from src.backtesting.walk_forward import _engine_for
from src.market_data.models import MarketTimeframe, OHLCBar


def compare_strategies(
    bars: List[OHLCBar],
    symbol: str,
    timeframe: MarketTimeframe,
    config: BacktestConfig,
    strategies: List[str],
    engine_factory=None,
) -> Dict[str, Any]:
    """Run each strategy individually and together; return comparison results."""
    analyzer = PerformanceAnalyzer()
    results: Dict[str, Any] = {"individual": {}, "combined": {}}

    for name in strategies:
        cfg = replace(config, name=f"{config.name}:{name}", strategies=[name])
        engine = (engine_factory or _engine_for)(cfg, symbol, timeframe, bars)
        result = engine.run()
        results["individual"][name] = analyzer.summary(result)

    # Combined run with all listed strategies enabled together.
    combined_cfg = replace(config, name=f"{config.name}:combined", strategies=list(strategies))
    combined_engine = (engine_factory or _engine_for)(combined_cfg, symbol, timeframe, bars)
    combined_result = combined_engine.run()
    results["combined"] = analyzer.summary(combined_result)
    results["combined_trades"] = combined_result.total_trades
    return results