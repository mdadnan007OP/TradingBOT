"""Persistence: save and load backtest results to/from JSON.

Only plain, serializable data is stored. Simulated results are clearly marked as
historical backtest output.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.backtesting.models import (
    BacktestResult,
    ClosedTrade,
    EquityPoint,
    EventType,
    ExitReason,
    OrderSide,
)


def _dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def save_result(result: BacktestResult, path: str) -> None:
    """Persist a BacktestResult to JSON (without the full event stream)."""
    data = {
        "config_name": result.config_name,
        "symbols": result.symbols,
        "timeframes": result.timeframes,
        "start_time": result.start_time.isoformat() if result.start_time else None,
        "end_time": result.end_time.isoformat() if result.end_time else None,
        "warnings": result.warnings,
        "metadata": result.metadata,
        "equity_curve": [
            {
                "timestamp": p.timestamp.isoformat() if p.timestamp else None,
                "equity": str(p.equity),
                "balance": str(p.balance),
                "margin": str(p.margin),
                "drawdown_percent": str(p.drawdown_percent),
                "open_positions": p.open_positions,
            }
            for p in result.equity_curve
        ],
        "trades": [
            {
                "trade_id": t.trade_id,
                "symbol": t.symbol,
                "side": t.side.value,
                "volume": str(t.volume),
                "entry_price": str(t.entry_price),
                "exit_price": str(t.exit_price),
                "entry_time": t.entry_time.isoformat() if t.entry_time else None,
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                "exit_reason": t.exit_reason.value if t.exit_reason else None,
                "strategy_name": t.strategy_name,
                "gross_pnl_quote": str(t.gross_pnl_quote),
                "net_pnl_account": str(t.net_pnl_account),
                "commission": str(t.commission),
                "swap": str(t.swap),
                "slippage_quote": str(t.slippage_quote),
                "r_multiple": str(t.r_multiple) if t.r_multiple is not None else None,
                "ambiguous_exit": t.ambiguous_exit,
            }
            for t in result.trades
        ],
        "disclaimer": "Simulated historical backtest results; not a guarantee of future performance.",
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def load_result(path: str) -> BacktestResult:
    """Load a BacktestResult previously saved with save_result."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    equity_curve: List[EquityPoint] = []
    for p in data.get("equity_curve", []):
        equity_curve.append(EquityPoint(
            timestamp=_dt(p["timestamp"]),
            equity=Decimal(p["equity"]),
            balance=Decimal(p["balance"]),
            margin=Decimal(p["margin"]),
            drawdown_percent=Decimal(p["drawdown_percent"]),
            open_positions=p.get("open_positions", 0),
        ))

    trades: List[ClosedTrade] = []
    for t in data.get("trades", []):
        trades.append(ClosedTrade(
            trade_id=t["trade_id"],
            position_id=t.get("position_id", t["trade_id"]),
            symbol=t["symbol"],
            side=OrderSide(t["side"]),
            volume=Decimal(t["volume"]),
            entry_price=Decimal(t["entry_price"]),
            exit_price=Decimal(t["exit_price"]),
            entry_time=_dt(t["entry_time"]),
            exit_time=_dt(t["exit_time"]),
            exit_reason=ExitReason(t["exit_reason"]) if t.get("exit_reason") else ExitReason.MANUAL,
            strategy_name=t["strategy_name"],
            gross_pnl_quote=Decimal(t["gross_pnl_quote"]),
            net_pnl_account=Decimal(t["net_pnl_account"]),
            commission=Decimal(t["commission"]),
            swap=Decimal(t["swap"]),
            slippage_quote=Decimal(t["slippage_quote"]),
            r_multiple=Decimal(t["r_multiple"]) if t.get("r_multiple") else None,
            ambiguous_exit=t.get("ambiguous_exit", False),
        ))

    return BacktestResult(
        config_name=data["config_name"],
        symbols=data["symbols"],
        timeframes=data["timeframes"],
        start_time=_dt(data.get("start_time")),
        end_time=_dt(data.get("end_time")),
        equity_curve=equity_curve,
        trades=trades,
        warnings=data.get("warnings", []),
        metadata=data.get("metadata", {}),
    )