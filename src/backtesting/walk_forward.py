"""Walk-forward and out-of-sample testing.

Splits historical data chronologically (NEVER randomly shuffled) into rolling
train/test windows. Out-of-sample performance is measured on the test region
only; the train region is prepended to provide indicator warm-up without leaking
future observations (the engine reveals bars chronologically).

Guardrails:
    * Time-series order is preserved; no shuffling.
    * Parameters are not optimized against the out-of-sample period here
      (see optimization.py, which only tunes on train windows).
    * Each window is reported independently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.backtesting.config import BacktestConfig
from src.backtesting.data_loader import BacktestDataLoader
from src.backtesting.engine import BacktestEngine
from src.backtesting.metrics import analyze_performance
from src.backtesting.models import BacktestResult
from src.market_data.models import MarketTimeframe, OHLCBar


@dataclass
class WalkForwardWindow:
    index: int
    train_bars: List[OHLCBar]
    test_bars: List[OHLCBar]


def rolling_windows(
    bars: List[OHLCBar],
    train_size: int,
    test_size: int,
    step: Optional[int] = None,
) -> List[WalkForwardWindow]:
    """Build rolling chronological train/test windows.

    Raises ValueError if sizes are invalid.
    """
    if train_size < 1 or test_size < 1:
        raise ValueError("train_size and test_size must be >= 1")
    step = step or test_size
    if step < 1:
        raise ValueError("step must be >= 1")
    windows: List[WalkForwardWindow] = []
    start = 0
    idx = 0
    while start + train_size + test_size <= len(bars):
        train = bars[start:start + train_size]
        test = bars[start + train_size:start + train_size + test_size]
        windows.append(WalkForwardWindow(index=idx, train_bars=train, test_bars=test))
        start += step
        idx += 1
    return windows


def _engine_for(config: BacktestConfig, symbol: str, tf: MarketTimeframe, bars: List[OHLCBar]) -> BacktestEngine:
    data = BacktestDataLoader().from_lists({(symbol, tf): bars})
    return BacktestEngine(config, data)


def run_walk_forward(
    bars: List[OHLCBar],
    symbol: str,
    timeframe: MarketTimeframe,
    config: BacktestConfig,
    train_size: int,
    test_size: int,
    step: Optional[int] = None,
    engine_factory=None,
) -> Dict[str, Any]:
    """Run a rolling walk-forward evaluation.

    Returns a dict with per-window results and an aggregate OOS summary.
    """
    windows = rolling_windows(bars, train_size, test_size, step)
    per_window: List[Dict[str, Any]] = []
    all_oos_trades = []
    oos_equity_start = None
    oos_equity_end = None

    for w in windows:
        combined = w.train_bars + w.test_bars
        engine = (engine_factory or _engine_for)(config, symbol, timeframe, combined)
        result = engine.run()

        test_start = w.test_bars[0].timestamp
        oos_trades = [t for t in result.trades if t.entry_time >= test_start]
        oos_curve = [p for p in result.equity_curve if p.timestamp >= test_start]
        starting = oos_curve[0].balance if oos_curve else None

        oos_report = analyze_performance(
            equity_curve=oos_curve,
            trades=oos_trades,
            starting_equity=starting if starting is not None else config.account.starting_balance,
        )
        per_window.append({
            "window": w.index,
            "train_start": w.train_bars[0].timestamp.isoformat(),
            "test_start": test_start.isoformat(),
            "test_end": w.test_bars[-1].timestamp.isoformat(),
            "oos_trades": len(oos_trades),
            "oos_net_profit": oos_report.net_profit,
            "oos_return_percent": oos_report.net_return_percent,
            "oos_max_drawdown_percent": oos_report.drawdown.max_drawdown_percent,
            "oos_win_rate_percent": oos_report.trade_stats.win_rate_percent,
        })
        all_oos_trades.extend(oos_trades)

    aggregate = {
        "num_windows": len(windows),
        "total_oos_trades": len(all_oos_trades),
        "note": (
            "Out-of-sample results use only each window's test region. Parameters "
            "must be tuned on train regions only (see optimization.py)."
        ),
    }
    return {"windows": per_window, "aggregate": aggregate}