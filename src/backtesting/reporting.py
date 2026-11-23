"""Reporting: serialize backtest results to JSON/CSV and human summaries.

Reports are derived from simulated results only and must be read as historical
backtest results — not guarantees of future performance.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.backtesting.models import BacktestResult, ClosedTrade, EquityPoint
from src.backtesting.performance import PerformanceAnalyzer, PerformanceReport


def _dec(value) -> Optional[str]:
    return None if value is None else str(value)


def report_to_dict(result: BacktestResult, include_events: bool = False) -> Dict[str, Any]:
    analyzer = PerformanceAnalyzer()
    report = analyzer.analyze(result)
    data: Dict[str, Any] = {
        "config": result.config_name,
        "symbols": result.symbols,
        "timeframes": result.timeframes,
        "start_time": result.start_time.isoformat() if result.start_time else None,
        "end_time": result.end_time.isoformat() if result.end_time else None,
        "performance": report.to_dict(),
        "warnings": result.warnings,
        "disclaimer": (
            "Historical backtest results are simulated and do not guarantee future "
            "performance."
        ),
    }
    if include_events:
        data["events"] = [
            {
                "type": e.event_type.value,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "symbol": e.symbol,
                "detail": e.detail,
            }
            for e in result.events
        ]
    return data


def report_to_json(result: BacktestResult, path: str, include_events: bool = False) -> None:
    data = report_to_dict(result, include_events=include_events)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def trades_to_csv(trades: List[ClosedTrade], path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "trade_id", "symbol", "side", "volume", "entry_time", "exit_time",
            "entry_price", "exit_price", "exit_reason", "strategy",
            "gross_pnl_quote", "net_pnl_account", "commission", "swap",
            "slippage_quote", "r_multiple", "ambiguous_exit",
        ])
        for t in trades:
            writer.writerow([
                t.trade_id, t.symbol, t.side.value, str(t.volume),
                t.entry_time.isoformat() if t.entry_time else "",
                t.exit_time.isoformat() if t.exit_time else "",
                str(t.entry_price), str(t.exit_price),
                t.exit_reason.value if t.exit_reason else "",
                t.strategy_name, str(t.gross_pnl_quote), str(t.net_pnl_account),
                str(t.commission), str(t.swap), str(t.slippage_quote),
                str(t.r_multiple) if t.r_multiple is not None else "",
                t.ambiguous_exit,
            ])


def equity_curve_to_csv(points: List[EquityPoint], path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["timestamp", "equity", "balance", "margin", "open_positions", "drawdown_percent"])
        for p in points:
            writer.writerow([
                p.timestamp.isoformat() if p.timestamp else "",
                str(p.equity), str(p.balance), str(p.margin),
                p.open_positions, str(p.drawdown_percent),
            ])


def monthly_performance(points: List[EquityPoint]) -> Dict[str, Dict[str, float]]:
    """Aggregate equity-curve change by calendar month (UTC)."""
    by_month: Dict[str, List[EquityPoint]] = {}
    for p in points:
        if p.timestamp is None:
            continue
        key = p.timestamp.strftime("%Y-%m")
        by_month.setdefault(key, []).append(p)
    result: Dict[str, Dict[str, float]] = {}
    for month, pts in sorted(by_month.items()):
        start = float(pts[0].equity)
        end = float(pts[-1].equity)
        change = end - start
        result[month] = {
            "start_equity": start,
            "end_equity": end,
            "change": change,
            "return_percent": (change / start * 100.0) if start else 0.0,
        }
    return result


def format_summary(result: BacktestResult) -> str:
    """Return a compact human-readable text summary."""
    report: PerformanceReport = PerformanceAnalyzer().analyze(result)
    ts = report.trade_stats
    lines = [
        f"Backtest: {result.config_name}  [{', '.join(result.symbols)}]",
        f"Period: {result.start_time} -> {result.end_time}",
        f"Starting equity: {report.starting_equity:.2f}  Ending equity: {report.ending_equity:.2f}",
        f"Net profit: {report.net_profit:.2f} ({report.net_return_percent:.2f}%)",
        f"Trades: {ts.total_trades}  Win rate: {ts.win_rate_percent:.1f}%  "
        f"Profit factor: {ts.profit_factor if ts.profit_factor is not None else 'n/a'}",
        f"Max drawdown: {report.drawdown.max_drawdown_percent:.2f}%  "
        f"Sharpe: {report.sharpe_ratio if report.sharpe_ratio is not None else 'n/a'}  "
        f"Sortino: {report.sortino_ratio if report.sortino_ratio is not None else 'n/a'}",
        f"Total costs: {report.total_costs:.2f} (commission {report.total_commission:.2f}, swap {report.total_swap:.2f})",
        f"Annualization: {report.annualization}",
        "Disclaimer: historical backtest results; not a guarantee of future performance.",
    ]
    for w in report.warnings:
        lines.append(f"WARNING: {w}")
    return "\n".join(lines)


def write_all(result: BacktestResult, out_dir: str, include_events: bool = False) -> Dict[str, str]:
    """Write JSON report, trades CSV, and equity-curve CSV. Returns paths."""
    import os

    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, f"{result.config_name}_report.json")
    trades_path = os.path.join(out_dir, f"{result.config_name}_trades.csv")
    equity_path = os.path.join(out_dir, f"{result.config_name}_equity.csv")
    report_to_json(result, json_path, include_events=include_events)
    trades_to_csv(result.trades, trades_path)
    equity_curve_to_csv(result.equity_curve, equity_path)
    return {"json": json_path, "trades": trades_path, "equity": equity_path}