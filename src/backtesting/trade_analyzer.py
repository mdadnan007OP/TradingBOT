"""Trade statistics analyzer.

Computes per-trade and aggregate statistics from closed trades.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from src.backtesting.models import ClosedTrade, ExitReason


@dataclass
class TradeStatistics:
    total_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate_percent: float
    gross_profit: float
    gross_loss: float
    net_profit: float
    profit_factor: Optional[float]
    average_trade: float
    average_win: float
    average_loss: float
    expectancy: float
    largest_win: float
    largest_loss: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    average_holding_seconds: Optional[float]
    r_units: float
    """Net profit expressed in risk units (sum of R-multiples)."""
    exits_by_reason: Dict[str, int] = field(default_factory=dict)


def _f(value: Optional[Decimal]) -> float:
    return float(value) if value is not None else 0.0


def analyze_trades(trades: List[ClosedTrade]) -> TradeStatistics:
    total = len(trades)
    if total == 0:
        return TradeStatistics(
            total_trades=0, winning_trades=0, losing_trades=0, breakeven_trades=0,
            win_rate_percent=0.0, gross_profit=0.0, gross_loss=0.0, net_profit=0.0,
            profit_factor=None, average_trade=0.0, average_win=0.0, average_loss=0.0,
            expectancy=0.0, largest_win=0.0, largest_loss=0.0,
            max_consecutive_wins=0, max_consecutive_losses=0,
            average_holding_seconds=None, r_units=0.0, exits_by_reason={},
        )

    pnls = [_f(t.net_pnl_account) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    breakeven = [p for p in pnls if p == 0]

    gross_profit = sum(wins)
    gross_loss = -sum(losses)  # positive magnitude
    net_profit = sum(pnls)

    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (
        float("inf") if gross_profit > 0 else None
    )

    average_trade = net_profit / total
    average_win = (gross_profit / len(wins)) if wins else 0.0
    average_loss = (sum(losses) / len(losses)) if losses else 0.0
    expectancy = average_trade

    # Consecutive streaks.
    max_consec_wins = 0
    max_consec_losses = 0
    cur_w = 0
    cur_l = 0
    for p in pnls:
        if p > 0:
            cur_w += 1
            cur_l = 0
        elif p < 0:
            cur_l += 1
            cur_w = 0
        else:
            cur_w = 0
            cur_l = 0
        max_consec_wins = max(max_consec_wins, cur_w)
        max_consec_losses = max(max_consec_losses, cur_l)

    holdings = [t.holding_seconds for t in trades if t.holding_seconds is not None]
    avg_hold = (sum(holdings) / len(holdings)) if holdings else None

    r_values = [float(t.r_multiple) for t in trades if t.r_multiple is not None]
    r_units = sum(r_values)

    exits: Dict[str, int] = {}
    for t in trades:
        reason = t.exit_reason.value if isinstance(t.exit_reason, ExitReason) else str(t.exit_reason)
        exits[reason] = exits.get(reason, 0) + 1

    return TradeStatistics(
        total_trades=total,
        winning_trades=len(wins),
        losing_trades=len(losses),
        breakeven_trades=len(breakeven),
        win_rate_percent=(len(wins) / total * 100.0),
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_profit=net_profit,
        profit_factor=profit_factor,
        average_trade=average_trade,
        average_win=average_win,
        average_loss=average_loss,
        expectancy=expectancy,
        largest_win=max(wins) if wins else 0.0,
        largest_loss=min(losses) if losses else 0.0,
        max_consecutive_wins=max_consec_wins,
        max_consecutive_losses=max_consec_losses,
        average_holding_seconds=avg_hold,
        r_units=r_units,
        exits_by_reason=exits,
    )


def group_by(trades: List[ClosedTrade], key_fn) -> Dict[str, List[ClosedTrade]]:
    """Group trades by an arbitrary key function (strategy/symbol/etc.)."""
    groups: Dict[str, List[ClosedTrade]] = {}
    for t in trades:
        k = str(key_fn(t))
        groups.setdefault(k, []).append(t)
    return groups


def performance_by_strategy(trades: List[ClosedTrade]) -> Dict[str, TradeStatistics]:
    return {k: analyze_trades(v) for k, v in group_by(trades, lambda t: t.strategy_name).items()}


def performance_by_symbol(trades: List[ClosedTrade]) -> Dict[str, TradeStatistics]:
    return {k: analyze_trades(v) for k, v in group_by(trades, lambda t: t.symbol).items()}