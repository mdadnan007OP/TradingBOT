"""Monte Carlo trade-sequence analysis.

Resamples the realized closed trades (with replacement) to build simulated
distributions of equity curves, drawdowns and risk-limit breach frequency.

All resampled outcomes are *simulated* and do NOT guarantee future results.
Returns are drawn from the empirical trade PnL distribution; no parametric
assumption is made beyond the observed trade sequence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.backtesting.models import ClosedTrade


@dataclass
class MonteCarloResult:
    """Results of a Monte Carlo trade-sequence resampling."""

    run_id: str
    generated_at: datetime
    seed: int
    num_trades: int
    num_simulations: int
    starting_equity: Decimal

    # --- Equity / return distributions ---
    final_equity_mean: float
    final_equity_median: float
    final_equity_p5: float
    final_equity_p95: float
    final_equity_min: float
    final_equity_max: float

    # --- Drawdown distributions ---
    max_drawdown_mean: float
    max_drawdown_median: float
    max_drawdown_p95: float
    max_drawdown_max: float

    # --- Risk-limit breach frequency ---
    breach_limit_percent: Optional[Decimal]
    breach_frequency: float
    """Fraction of simulations that exceeded breach_limit_percent."""

    # --- Per-simulation summaries ---
    simulations: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "seed": self.seed,
            "num_trades": self.num_trades,
            "num_simulations": self.num_simulations,
            "starting_equity": str(self.starting_equity),
            "final_equity": {
                "mean": self.final_equity_mean,
                "median": self.final_equity_median,
                "p5": self.final_equity_p5,
                "p95": self.final_equity_p95,
                "min": self.final_equity_min,
                "max": self.final_equity_max,
            },
            "max_drawdown": {
                "mean": self.max_drawdown_mean,
                "median": self.max_drawdown_median,
                "p95": self.max_drawdown_p95,
                "max": self.max_drawdown_max,
            },
            "risk_limit": {
                "breach_limit_percent": (
                    str(self.breach_limit_percent) if self.breach_limit_percent is not None else None
                ),
                "breach_frequency": self.breach_frequency,
            },
            "disclaimer": (
                "Resampled outcomes are simulated and do not guarantee future results."
            ),
        }


def _percentile(sorted_values: List[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    s = sorted(sorted_values)
    k = (len(s) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def _max_drawdown(equities: List[float]) -> float:
    peak = None
    worst = 0.0
    for eq in equities:
        if peak is None or eq > peak:
            peak = eq
        if peak and peak > 0:
            dd = (peak - eq) / peak
            if dd > worst:
                worst = dd
    return worst


def run_monte_carlo(
    trades: List[ClosedTrade],
    *,
    num_simulations: int = 1000,
    seed: int = 42,
    starting_equity: Optional[Decimal] = None,
    breach_limit_percent: Optional[Decimal] = None,
    bar_interval_seconds: Optional[float] = None,
    run_id: Optional[str] = None,
) -> MonteCarloResult:
    """Run Monte Carlo trade-sequence resampling.

    Each simulation draws ``num_trades`` trades with replacement from the
    observed closed trades and compounds their PnL from ``starting_equity``.
    """
    import random

    if not trades:
        # Degenerate: no trades to resample.
        empty = MonteCarloResult(
            run_id=run_id or "mc-empty",
            generated_at=datetime.now(timezone.utc),
            seed=seed,
            num_trades=0,
            num_simulations=num_simulations,
            starting_equity=starting_equity or Decimal("0"),
            final_equity_mean=0.0,
            final_equity_median=0.0,
            final_equity_p5=0.0,
            final_equity_p95=0.0,
            final_equity_min=0.0,
            final_equity_max=0.0,
            max_drawdown_mean=0.0,
            max_drawdown_median=0.0,
            max_drawdown_p95=0.0,
            max_drawdown_max=0.0,
            breach_limit_percent=breach_limit_percent,
            breach_frequency=0.0,
        )
        return empty

    rng = random.Random(seed)
    start_eq = starting_equity or Decimal("0")
    start_eq_float = float(start_eq)

    pnls = [float(t.net_pnl_account) for t in trades]
    n = len(trades)

    final_equities: List[float] = []
    max_dds: List[float] = []
    simulations: List[Dict[str, Any]] = []
    breach_count = 0

    for _ in range(num_simulations):
        drawn = [pnls[rng.randrange(n)] for _ in range(n)]
        # Build equity curve directly from the drawn PnL sequence.
        equity = start_eq_float
        curve = [equity]
        for p in drawn:
            equity += p
            curve.append(equity)
        final_equity = equity
        max_dd = _max_drawdown(curve)
        final_equities.append(final_equity)
        max_dds.append(max_dd)
        sim = {
            "final_equity": final_equity,
            "max_drawdown_percent": max_dd * 100.0,
            "net_return_percent": ((final_equity - start_eq_float) / start_eq_float * 100.0)
            if start_eq_float else 0.0,
        }
        simulations.append(sim)
        if breach_limit_percent is not None and max_dd * 100.0 >= float(breach_limit_percent):
            breach_count += 1

    final_equities_sorted = sorted(final_equities)
    max_dds_sorted = sorted(max_dds)

    breach_frequency = (breach_count / num_simulations) if num_simulations else 0.0

    return MonteCarloResult(
        run_id=run_id or "mc",
        generated_at=datetime.now(timezone.utc),
        seed=seed,
        num_trades=n,
        num_simulations=num_simulations,
        starting_equity=start_eq,
        final_equity_mean=sum(final_equities) / len(final_equities),
        final_equity_median=_percentile(final_equities_sorted, 50.0),
        final_equity_p5=_percentile(final_equities_sorted, 5.0),
        final_equity_p95=_percentile(final_equities_sorted, 95.0),
        final_equity_min=final_equities_sorted[0],
        final_equity_max=final_equities_sorted[-1],
        max_drawdown_mean=sum(max_dds) / len(max_dds),
        max_drawdown_median=_percentile(max_dds_sorted, 50.0),
        max_drawdown_p95=_percentile(max_dds_sorted, 95.0),
        max_drawdown_max=max_dds_sorted[-1],
        breach_limit_percent=breach_limit_percent,
        breach_frequency=breach_frequency,
        simulations=simulations[: min(num_simulations, 50)],  # cap stored detail
    )
