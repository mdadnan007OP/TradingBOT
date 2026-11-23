"""Tests for performance metrics, trade statistics, and drawdown analysis."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from src.backtesting.metrics import analyze_performance
from src.backtesting.models import ClosedTrade, EquityPoint, ExitReason, OrderSide
from src.backtesting.trade_analyzer import analyze_trades
from src.backtesting.drawdown_analysis import analyze_drawdown
from tests.backtesting.conftest import BASE


def _trade(pnl, symbol="EURUSD", strategy="S", r=None, side=OrderSide.LONG):
    return ClosedTrade(
        trade_id=f"t-{pnl}-{symbol}",
        position_id="p",
        symbol=symbol,
        side=side,
        volume=Decimal("1"),
        entry_price=Decimal("1.1000"),
        exit_price=Decimal("1.1010"),
        entry_time=BASE,
        exit_time=BASE + timedelta(hours=1),
        exit_reason=ExitReason.MANUAL,
        strategy_name=strategy,
        gross_pnl_quote=Decimal(str(pnl)),
        net_pnl_account=Decimal(str(pnl)),
        r_multiple=Decimal(str(r)) if r is not None else None,
    )


def _curve(equities):
    return [
        EquityPoint(timestamp=BASE + timedelta(hours=i), equity=Decimal(str(e)), balance=Decimal(str(e)))
        for i, e in enumerate(equities)
    ]


def test_trade_statistics_basic():
    trades = [_trade(100), _trade(-50), _trade(0), _trade(200)]
    stats = analyze_trades(trades)
    assert stats.total_trades == 4
    assert stats.winning_trades == 2
    assert stats.losing_trades == 1
    assert stats.breakeven_trades == 1
    assert stats.win_rate_percent == 50.0
    assert stats.gross_profit == 300
    assert stats.gross_loss == 50
    assert stats.net_profit == 250
    assert stats.profit_factor == 6.0


def test_consecutive_streaks():
    trades = [_trade(10), _trade(10), _trade(-5), _trade(-5), _trade(-5), _trade(10)]
    stats = analyze_trades(trades)
    assert stats.max_consecutive_wins == 2
    assert stats.max_consecutive_losses == 3


def test_drawdown_analysis():
    curve = _curve([100, 120, 90, 110, 130])
    dd = analyze_drawdown(curve)
    # Max drawdown from 120 -> 90 = 25%
    assert abs(dd.max_drawdown_percent - 25.0) < 1e-6
    assert dd.max_drawdown_amount == 30


def test_performance_report():
    curve = _curve([100, 110, 105, 120, 130])
    trades = [_trade(10), _trade(-5), _trade(20)]
    report = analyze_performance(curve, trades, starting_equity=Decimal("100"))
    assert report.starting_equity == 100
    assert report.ending_equity == 130
    assert report.net_profit == 30
    assert report.net_return_percent == 30.0
    assert report.trade_stats.total_trades == 3


def test_performance_by_strategy_and_symbol():
    trades = [
        _trade(10, symbol="EURUSD", strategy="A"),
        _trade(-5, symbol="EURUSD", strategy="A"),
        _trade(20, symbol="XAUUSD", strategy="B"),
    ]
    curve = _curve([100, 110, 105, 120])
    report = analyze_performance(curve, trades, starting_equity=Decimal("100"))
    assert "A" in report.by_strategy
    assert "B" in report.by_strategy
    assert "EURUSD" in report.by_symbol


def test_insufficient_trades_warning():
    curve = _curve([100, 110])
    trades = [_trade(10)]
    report = analyze_performance(curve, trades, starting_equity=Decimal("100"))
    assert any("not statistically reliable" in w for w in report.warnings)


def test_r_units():
    trades = [_trade(10, r=1.0), _trade(-5, r=-0.5), _trade(20, r=2.0)]
    stats = analyze_trades(trades)
    assert stats.r_units == 2.5