"""Performance analysis facade.

Combines metrics, drawdown, and trade statistics into a single report for a
:class:`~src.backtesting.models.BacktestResult`.
"""

from __future__ import annotations

from src.backtesting.metrics import PerformanceReport, analyze_performance
from src.backtesting.models import BacktestResult
from decimal import Decimal


class PerformanceAnalyzer:
    """Computes a PerformanceReport from a BacktestResult."""

    def analyze(self, result: BacktestResult) -> PerformanceReport:
        starting = result.equity_curve[0].balance if result.equity_curve else Decimal("0")
        if result.final_balance is not None and not result.equity_curve:
            starting = Decimal("0")
        # Prefer the configured starting balance recorded in metadata.
        meta = result.metadata.get("config", {})
        try:
            starting = Decimal(str(meta["account"]["starting_balance"]))
        except (KeyError, ValueError, TypeError):
            pass
        warnings = list(result.warnings)
        return analyze_performance(
            equity_curve=result.equity_curve,
            trades=result.trades,
            starting_equity=starting,
            warnings=warnings,
        )

    def summary(self, result: BacktestResult) -> dict:
        """Return a compact summary dict."""
        report = self.analyze(result)
        return {
            "config": result.config_name,
            "symbols": result.symbols,
            "net_profit": report.net_profit,
            "net_return_percent": report.net_return_percent,
            "total_trades": report.trade_stats.total_trades,
            "win_rate_percent": report.trade_stats.win_rate_percent,
            "profit_factor": report.trade_stats.profit_factor,
            "max_drawdown_percent": report.drawdown.max_drawdown_percent,
            "sharpe_ratio": report.sharpe_ratio,
            "sortino_ratio": report.sortino_ratio,
            "ending_equity": report.ending_equity,
            "warnings": report.warnings,
        }