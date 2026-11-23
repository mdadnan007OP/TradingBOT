"""Controlled parameter optimization.

Grid search over explicit parameter ranges, evaluated on historical training
windows. Selection uses a robustness score (return, drawdown, trade count and
profit factor) — NOT net profit alone — to reduce overfitting.

Guarantees:
    * Original strategy configuration is never mutated (configs are copied).
    * Optimization only evaluates the data it is given (train region); callers
      must validate on a separate out-of-sample period (see walk_forward.py).
    * Candidates with too few trades are rejected as non-robust.
"""

from __future__ import annotations

import itertools
from dataclasses import replace
from typing import Any, Callable, Dict, List, Optional

from src.backtesting.config import BacktestConfig
from src.backtesting.engine import BacktestEngine
from src.backtesting.performance import PerformanceAnalyzer
from src.backtesting.walk_forward import _engine_for
from src.market_data.models import MarketTimeframe, OHLCBar

MIN_TRADES_FOR_ROBUSTNESS = 10


def robustness_score(summary: Dict[str, Any]) -> float:
    """A robustness score (higher is better). Penalizes drawdown and low sample."""
    trades = summary.get("total_trades", 0)
    if trades < MIN_TRADES_FOR_ROBUSTNESS:
        return float("-inf")
    ret = summary.get("net_return_percent", 0.0) or 0.0
    dd = summary.get("max_drawdown_percent", 0.0) or 0.0
    pf = summary.get("profit_factor")
    pf_val = pf if isinstance(pf, (int, float)) else 0.0
    # Weighted blend: reward return & profit factor, penalize drawdown.
    return ret - 0.5 * dd + 2.0 * pf_val


def grid_search(
    bars: List[OHLCBar],
    symbol: str,
    timeframe: MarketTimeframe,
    config: BacktestConfig,
    strategy_name: str,
    param_grid: Dict[str, List[Any]],
    engine_factory: Optional[Callable] = None,
    score_fn: Optional[Callable[[Dict[str, Any]], float]] = None,
) -> List[Dict[str, Any]]:
    """Exhaustive grid search over ``param_grid`` for one strategy.

    Returns candidates sorted by descending robustness score.
    """
    if not param_grid:
        raise ValueError("param_grid must not be empty")
    keys = list(param_grid.keys())
    value_lists = [param_grid[k] for k in keys]
    analyzer = PerformanceAnalyzer()
    score_fn = score_fn or robustness_score

    results: List[Dict[str, Any]] = []
    for combo in itertools.product(*value_lists):
        overrides = {keys[i]: combo[i] for i in range(len(keys))}
        cfg = replace(
            config,
            name=f"opt:{strategy_name}",
            strategies=[strategy_name],
            strategy_parameters={strategy_name: overrides},
        )
        engine = (engine_factory or _engine_for)(cfg, symbol, timeframe, bars)
        result = engine.run()
        summary = analyzer.summary(result)
        results.append({
            "params": overrides,
            "score": score_fn(summary),
            "summary": summary,
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def best_candidate(results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return the highest-scoring candidate, or None if there are none.

    Non-robust candidates (score == -inf) are only returned if nothing better
    exists, so callers can still inspect them.
    """
    if not results:
        return None
    robust = [r for r in results if r["score"] != float("-inf")]
    pool = robust or results
    return max(pool, key=lambda r: r["score"])