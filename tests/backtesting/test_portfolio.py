"""Tests for the portfolio/account simulator."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from src.backtesting.config import (
    AccountConfig,
    CommissionConfig,
    CommissionModel,
    ExecutionConfig,
    SlippageConfig,
    SlippageModel,
    SpreadConfig,
)
from src.backtesting.cost_model import TransactionCostModel
from src.backtesting.execution_simulator import ExecutionSimulator
from src.backtesting.models import ExitReason, OrderSide
from src.backtesting.portfolio_simulator import PortfolioSimulator
from src.market_data.models import InstrumentSpec, InstrumentType, spec_for_symbol
from tests.backtesting.conftest import BASE


def _portfolio(account=None, commission=None):
    account = account or AccountConfig(starting_balance=Decimal("10000"), currency="USD", leverage=Decimal("30"))
    exec_cfg = ExecutionConfig(
        spread=SpreadConfig(fixed_spread={"EURUSD": Decimal("0")}),
        slippage=SlippageConfig(model=SlippageModel.NONE),
        commission=commission or CommissionConfig(model=CommissionModel.NONE),
    )
    costs = TransactionCostModel(exec_cfg)
    ex = ExecutionSimulator(exec_cfg, costs)
    specs = {"EURUSD": spec_for_symbol("EURUSD")}
    return PortfolioSimulator(account, costs, ex, specs)


def test_open_and_close_position_updates_balance():
    pf = _portfolio()
    pos = pf.open_position(
        symbol="EURUSD", side=OrderSide.LONG, volume=Decimal("1"),
        fill_price=Decimal("1.1000"), fill_time=BASE,
    )
    assert pos is not None
    assert pf.balance == Decimal("10000")
    trade = pf.close_position(pos, exit_price=Decimal("1.1010"), exit_time=BASE + timedelta(hours=1), exit_reason=ExitReason.MANUAL)
    # Profit = (1.1010-1.1000)*1 * contract 100000 * rate 1 = 100
    assert trade.net_pnl_account == Decimal("100")
    assert pf.balance == Decimal("10100")


def test_short_position_pnl():
    pf = _portfolio()
    pos = pf.open_position(
        symbol="EURUSD", side=OrderSide.SHORT, volume=Decimal("1"),
        fill_price=Decimal("1.1000"), fill_time=BASE,
    )
    trade = pf.close_position(pos, exit_price=Decimal("1.0990"), exit_time=BASE + timedelta(hours=1), exit_reason=ExitReason.MANUAL)
    # Short profit = (1.1000-1.0990)*100000 = 100
    assert trade.net_pnl_account == Decimal("100")


def test_commission_reduces_pnl():
    pf = _portfolio(commission=CommissionConfig(model=CommissionModel.PER_TRADE, per_trade=Decimal("5")))
    pos = pf.open_position(
        symbol="EURUSD", side=OrderSide.LONG, volume=Decimal("1"),
        fill_price=Decimal("1.1000"), fill_time=BASE,
    )
    trade = pf.close_position(pos, exit_price=Decimal("1.1010"), exit_time=BASE + timedelta(hours=1), exit_reason=ExitReason.MANUAL)
    # Gross 100 - commission 5 = 95
    assert trade.net_pnl_account == Decimal("95")


def test_equity_includes_unrealized():
    pf = _portfolio()
    pf.open_position(
        symbol="EURUSD", side=OrderSide.LONG, volume=Decimal("1"),
        fill_price=Decimal("1.1000"), fill_time=BASE,
    )
    equity = pf.equity({"EURUSD": Decimal("1.1010")})
    # balance 10000 + unrealized 100
    assert equity == Decimal("10100")


def test_used_margin():
    pf = _portfolio()
    pf.open_position(
        symbol="EURUSD", side=OrderSide.LONG, volume=Decimal("1"),
        fill_price=Decimal("1.1000"), fill_time=BASE,
    )
    margin = pf.used_margin({"EURUSD": Decimal("1.1000")})
    # notional = 1 * 1.1000 * 100000 = 110000; /30 leverage = 3666.67
    assert margin == (Decimal("110000") / Decimal("30"))


def test_netting_rejects_second_position():
    pf = _portfolio(account=AccountConfig(
        starting_balance=Decimal("10000"), currency="USD", leverage=Decimal("30"),
        position_mode="netting",
    ))
    pf.open_position("EURUSD", OrderSide.LONG, Decimal("1"), Decimal("1.1000"), BASE)
    second = pf.open_position("EURUSD", OrderSide.SHORT, Decimal("1"), Decimal("1.1000"), BASE)
    assert second is None
    assert len(pf.rejected) == 1


def test_close_all_closes_open_positions():
    pf = _portfolio()
    pf.open_position("EURUSD", OrderSide.LONG, Decimal("1"), Decimal("1.1000"), BASE)
    closed = pf.close_all({"EURUSD": Decimal("1.1005")}, BASE + timedelta(hours=1))
    assert len(closed) == 1
    assert pf.equity({"EURUSD": Decimal("1.1005")}) == pf.balance


def test_check_exits_closes_on_stop():
    pf = _portfolio()
    from tests.backtesting.conftest import make_bar
    from src.market_data.models import MarketTimeframe
    pos = pf.open_position(
        symbol="EURUSD", side=OrderSide.LONG, volume=Decimal("1"),
        fill_price=Decimal("1.1000"), fill_time=BASE, stop_loss_price=Decimal("1.0990"),
    )
    bar = make_bar("EURUSD", MarketTimeframe.H1, BASE + timedelta(hours=1), 1.1000, 1.1010, 1.0985, 1.0995)
    closed = pf.check_exits("EURUSD", bar)
    assert len(closed) == 1
    assert closed[0].exit_reason == ExitReason.STOP_LOSS


def test_equity_curve_drawdown_recorded():
    pf = _portfolio()
    pf.open_position("EURUSD", OrderSide.LONG, Decimal("1"), Decimal("1.1000"), BASE)
    pf.record_equity_point(BASE, {"EURUSD": Decimal("1.1000")})
    pf.record_equity_point(BASE + timedelta(hours=1), {"EURUSD": Decimal("1.0990")})
    last = pf.equity_curve[-1]
    assert last.drawdown_percent > 0