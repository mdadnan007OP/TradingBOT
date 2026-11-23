"""Tests for the execution simulator: entries, spread, slippage, SL/TP, gaps, ambiguity."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.backtesting.config import (
    AmbiguousFillPolicy,
    CommissionConfig,
    CommissionModel,
    ExecutionConfig,
    SlippageConfig,
    SlippageModel,
    SpreadConfig,
)
from src.backtesting.cost_model import TransactionCostModel
from src.backtesting.execution_simulator import ExecutionSimulator
from src.backtesting.models import ExitReason, OrderSide, SimulatedPosition
from tests.backtesting.conftest import BASE, make_bar
from src.market_data.models import MarketTimeframe


def _exec(config: ExecutionConfig = None) -> ExecutionSimulator:
    config = config or ExecutionConfig(
        ambiguous_fill_policy=AmbiguousFillPolicy.CONSERVATIVE,
        spread=SpreadConfig(fixed_spread={"EURUSD": Decimal("0.0002")}),
        slippage=SlippageConfig(model=SlippageModel.NONE),
        commission=CommissionConfig(model=CommissionModel.NONE),
    )
    costs = TransactionCostModel(config)
    return ExecutionSimulator(config, costs)


def _bar(open_, high, low, close):
    return make_bar("EURUSD", MarketTimeframe.H1, BASE, open_, high, low, close)


def test_long_entry_uses_ask():
    ex = _exec()
    bar = _bar(1.1000, 1.1010, 1.0990, 1.1005)
    fill = ex.entry_fill("EURUSD", OrderSide.LONG, bar)
    # ask = open + half spread
    assert fill.base_price == Decimal("1.1001")
    assert fill.quote_side == "ask"


def test_short_entry_uses_bid():
    ex = _exec()
    bar = _bar(1.1000, 1.1010, 1.0990, 1.1005)
    fill = ex.entry_fill("EURUSD", OrderSide.SHORT, bar)
    assert fill.base_price == Decimal("1.0999")
    assert fill.quote_side == "bid"


def test_entry_applies_adverse_slippage():
    config = ExecutionConfig(
        ambiguous_fill_policy=AmbiguousFillPolicy.CONSERVATIVE,
        spread=SpreadConfig(fixed_spread={"EURUSD": Decimal("0")}),
        slippage=SlippageConfig(model=SlippageModel.FIXED_POINTS, fixed_points={"EURUSD": Decimal("0.0003")}),
    )
    ex = _exec(config)
    bar = _bar(1.1000, 1.1010, 1.0990, 1.1005)
    fill = ex.entry_fill("EURUSD", OrderSide.LONG, bar)
    assert fill.price == Decimal("1.1003")  # ask (1.1000) + slippage


def test_long_take_profit_hit():
    ex = _exec()
    pos = SimulatedPosition(
        position_id="p1", symbol="EURUSD", side=OrderSide.LONG, volume=Decimal("1"),
        entry_price=Decimal("1.1000"), entry_time=BASE,
        take_profit_price=Decimal("1.1010"),
    )
    bar = _bar(1.1000, 1.1015, 1.0990, 1.1012)  # high above TP
    res = ex.check_exit(pos, bar)
    assert res is not None
    assert res.reason == ExitReason.TAKE_PROFIT


def test_long_stop_loss_hit():
    ex = _exec()
    pos = SimulatedPosition(
        position_id="p1", symbol="EURUSD", side=OrderSide.LONG, volume=Decimal("1"),
        entry_price=Decimal("1.1000"), entry_time=BASE,
        stop_loss_price=Decimal("1.0990"),
    )
    bar = _bar(1.1000, 1.1010, 1.0985, 1.0995)  # low below SL
    res = ex.check_exit(pos, bar)
    assert res is not None
    assert res.reason == ExitReason.STOP_LOSS


def test_short_take_profit_and_stop():
    ex = _exec()
    tp_pos = SimulatedPosition(
        position_id="p1", symbol="EURUSD", side=OrderSide.SHORT, volume=Decimal("1"),
        entry_price=Decimal("1.1000"), entry_time=BASE,
        take_profit_price=Decimal("1.0990"),
    )
    bar = _bar(1.1000, 1.1010, 1.0985, 1.0988)
    assert ex.check_exit(tp_pos, bar).reason == ExitReason.TAKE_PROFIT

    sl_pos = SimulatedPosition(
        position_id="p2", symbol="EURUSD", side=OrderSide.SHORT, volume=Decimal("1"),
        entry_price=Decimal("1.1000"), entry_time=BASE,
        stop_loss_price=Decimal("1.1010"),
    )
    bar2 = _bar(1.1000, 1.1015, 1.0990, 1.1012)
    assert ex.check_exit(sl_pos, bar2).reason == ExitReason.STOP_LOSS


def test_gap_through_stop_loss_adverse_fill():
    ex = _exec()
    pos = SimulatedPosition(
        position_id="p1", symbol="EURUSD", side=OrderSide.LONG, volume=Decimal("1"),
        entry_price=Decimal("1.1000"), entry_time=BASE,
        stop_loss_price=Decimal("1.0990"),
    )
    # Bar opens at 1.0980 (gapped below stop) → fill at open, worse than stop.
    bar = _bar(1.0980, 1.0985, 1.0975, 1.0982)
    res = ex.check_exit(pos, bar)
    assert res is not None
    assert res.gapped is True
    # Exit price should reflect the gap open (~1.0980 side), worse than 1.0990.
    assert res.price < Decimal("1.0990")


def test_same_candle_ambiguity_conservative():
    config = ExecutionConfig(
        ambiguous_fill_policy=AmbiguousFillPolicy.CONSERVATIVE,
        spread=SpreadConfig(fixed_spread={"EURUSD": Decimal("0")}),
    )
    ex = _exec(config)
    pos = SimulatedPosition(
        position_id="p1", symbol="EURUSD", side=OrderSide.LONG, volume=Decimal("1"),
        entry_price=Decimal("1.1000"), entry_time=BASE,
        stop_loss_price=Decimal("1.0990"), take_profit_price=Decimal("1.1010"),
    )
    # One bar hits both SL and TP.
    bar = _bar(1.1000, 1.1020, 1.0980, 1.1000)
    res = ex.check_exit(pos, bar)
    assert res is not None
    assert res.ambiguous is True
    assert res.reason == ExitReason.STOP_LOSS  # conservative = stop first


def test_same_candle_ambiguity_optimistic():
    config = ExecutionConfig(
        ambiguous_fill_policy=AmbiguousFillPolicy.OPTIMISTIC,
        spread=SpreadConfig(fixed_spread={"EURUSD": Decimal("0")}),
    )
    ex = _exec(config)
    pos = SimulatedPosition(
        position_id="p1", symbol="EURUSD", side=OrderSide.LONG, volume=Decimal("1"),
        entry_price=Decimal("1.1000"), entry_time=BASE,
        stop_loss_price=Decimal("1.0990"), take_profit_price=Decimal("1.1010"),
    )
    bar = _bar(1.1000, 1.1020, 1.0980, 1.1000)
    res = ex.check_exit(pos, bar)
    assert res.reason == ExitReason.TAKE_PROFIT


def test_same_candle_ambiguity_skip():
    config = ExecutionConfig(
        ambiguous_fill_policy=AmbiguousFillPolicy.SKIP,
        spread=SpreadConfig(fixed_spread={"EURUSD": Decimal("0")}),
    )
    ex = _exec(config)
    pos = SimulatedPosition(
        position_id="p1", symbol="EURUSD", side=OrderSide.LONG, volume=Decimal("1"),
        entry_price=Decimal("1.1000"), entry_time=BASE,
        stop_loss_price=Decimal("1.0990"), take_profit_price=Decimal("1.1010"),
    )
    bar = _bar(1.1000, 1.1020, 1.0980, 1.1000)
    res = ex.check_exit(pos, bar)
    assert res is not None
    assert res.fill is False


def test_no_exit_when_neither_hit():
    ex = _exec()
    pos = SimulatedPosition(
        position_id="p1", symbol="EURUSD", side=OrderSide.LONG, volume=Decimal("1"),
        entry_price=Decimal("1.1000"), entry_time=BASE,
        stop_loss_price=Decimal("1.0950"), take_profit_price=Decimal("1.1050"),
    )
    bar = _bar(1.1000, 1.1010, 1.0990, 1.1005)
    assert ex.check_exit(pos, bar) is None