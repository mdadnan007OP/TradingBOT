"""Performance metrics: returns, risk-adjusted ratios, and trade stats.

All ratios document their annualization assumption. Risk-adjusted ratios are
computed from equity-curve returns; annualization uses the observed median bar
interval so results are reproducible for a given dataset.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from src.backtesting.drawdown_analysis import DrawdownAnalysis, analyze_drawdown
from src.backtesting.equity_curve import build_equity_curve
from src.backtesting.models import ClosedTrade, EquityPoint
from src.backtesting.trade_analyzer import (
    TradeStatistics,
    analyze_trades,
    performance_by_strategy,
    performance_by_symbol,
)

SECONDS_PER_YEAR = 365.25 * 24 * 3600


@dataclass
class PerformanceReport:
    """Comprehensive backtest performance report."""

    starting_equity: float
    ending_equity: float
    net_profit: float
    net_return_percent: float
    gross_profit: float
    gross_loss: float
    trade_stats: TradeStatistics
    drawdown: DrawdownAnalysis
    sharpe_ratio: Optional[float]
    sortino_ratio: Optional[float]
    return_volatility_percent: float
    annualization: str
    by_strategy: dict = field(default_factory=dict)
    by_symbol: dict = field(default_factory=dict)
    total_commission: float = 0.0
    total_swap: float = 0.0
    total_costs: float = 0.0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "starting_equity": self.starting_equity,
            "ending_equity": self.ending_equity,
            "net_profit": self.net_profit,
            "net_return_percent": self.net_return_percent,
            "gross_profit": self.gross_profit,
            "gross_loss": self.gross_loss,
            "trade_stats": self.trade_stats.__dict__,
            "drawdown": self.drawdown.__dict__,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "return_volatility_percent": self.return_volatility_percent,
            "annualization": self.annualization,
            "by_strategy": {k: v.__dict__ for k, v in self.by_strategy.items()},
            "by_symbol": {k: v.__dict__ for k, v in self.by_symbol.items()},
            "total_commission": self.total_commission,
            "total_swap": self.total_swap,
            "total_costs": self.total_costs,
            "warnings": self.warnings,
        }


def _median_interval_seconds(curve) -> Optional[float]:
    if len(curve) < 2:
        return None
    deltas = [
        (curve[i].timestamp - curve[i - 1].timestamp).total_seconds()
        for i in range(1, len(curve))
    ]
    deltas = [d for d in deltas if d > 0]
    if not deltas:
        return None
    deltas.sort()
    mid = len(deltas) // 2
    if len(deltas) % 2 == 1:
        return deltas[mid]
    return (deltas[mid - 1] + deltas[mid]) / 2


def _returns(equities: List[float]) -> List[float]:
    out: List[float] = []
    for i in range(1, len(equities)):
        prev = equities[i - 1]
        if prev != 0:
            out.append(equities[i] / prev - 1.0)
        else:
            out.append(0.0)
    return out


def _sharpe(returns: List[float], periods_per_year: Optional[float]) -> Optional[float]:
    if len(returns) < 2 or periods_per_year is None:
        return None
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(var)
    if std == 0:
        return None
    return (mean / std) * math.sqrt(periods_per_year)


def _sortino(returns: List[float], periods_per_year: Optional[float]) -> Optional[float]:
    if len(returns) < 2 or periods_per_year is None:
        return None
    mean = sum(returns) / len(returns)
    downside = [r for r in returns if r < 0]
    if not downside:
        return None
    downside_dev = math.sqrt(sum(r ** 2 for r in downside) / len(returns))
    if downside_dev == 0:
        return None
    return (mean / downside_dev) * math.sqrt(periods_per_year)


def analyze_performance(
    equity_curve: List[EquityPoint],
    trades: List[ClosedTrade],
    starting_equity: Decimal,
    warnings: Optional[List[str]] = None,
) -> PerformanceReport:
    """Compute a full PerformanceReport from an equity curve and closed trades."""
    warnings = list(warnings or [])
    curve = build_equity_curve(equity_curve)
    ending_equity = curve[-1].equity if curve else float(starting_equity)
    net_profit = ending_equity - float(starting_equity)
    net_return_pct = (net_profit / float(starting_equity) * 100.0) if starting_equity else 0.0

    trade_stats = analyze_trades(trades)
    drawdown = analyze_drawdown(equity_curve)

    equities = [c.equity for c in curve]
    returns = _returns(equities)
    median_interval = _median_interval_seconds(curve)
    periods_per_year = (SECONDS_PER_YEAR / median_interval) if median_interval else None
    annualization = (
        f"median_bar={median_interval:.0f}s; periods_per_year={periods_per_year:.1f}"
        if periods_per_year
        else "insufficient data for annualization"
    )
    if periods_per_year is None:
        warnings.append("Annualized ratios unavailable (insufficient curve data).")

    # Return volatility (annualized std of returns).
    volatility_pct = 0.0
    if len(returns) >= 2 and periods_per_year:
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        volatility_pct = math.sqrt(var) * math.sqrt(periods_per_year) * 100.0

    sharpe = _sharpe(returns, periods_per_year)
    sortino = _sortino(returns, periods_per_year)

    total_commission = sum(float(t.commission) for t in trades)
    total_swap = sum(float(t.swap) for t in trades)
    total_slippage = sum(float(t.slippage_quote) for t in trades)
    total_costs = total_commission + total_swap + total_slippage

    if len(trades) < 30:
        warnings.append(
            f"Only {len(trades)} trades: statistics are not statistically reliable."
        )

    return PerformanceReport(
        starting_equity=float(starting_equity),
        ending_equity=ending_equity,
        net_profit=net_profit,
        net_return_percent=net_return_pct,
        gross_profit=trade_stats.gross_profit,
        gross_loss=trade_stats.gross_loss,
        trade_stats=trade_stats,
        drawdown=drawdown,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        return_volatility_percent=volatility_pct,
        annualization=annualization,
        by_strategy=performance_by_strategy(trades),
        by_symbol=performance_by_symbol(trades),
        total_commission=total_commission,
        total_swap=total_swap,
        total_costs=total_costs,
        warnings=warnings,
    )