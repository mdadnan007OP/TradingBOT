"""Daily loss and drawdown tests."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.risk_management.base import AccountSnapshot
from src.risk_management.config import test_policy
from src.risk_management.drawdown import DrawdownTracker, DrawdownResult
from src.risk_management.models import DailyPnLState, DrawdownState


def _account(currency="USD", equity=Decimal("10000.00"), balance=Decimal("10000.00")):
    return AccountSnapshot(
        login=1, name="t", server="t", currency=currency,
        balance=balance, equity=equity, margin=Decimal("0"),
        free_margin=equity, trade_allowed=True, trade_mode="demo",
        timestamp=datetime.now(timezone.utc), data_source="mock",
    )


class TestDrawdown:
    def test_no_drawdown_at_peak(self):
        tracker = DrawdownTracker(Decimal("0.10"), Decimal("0.15"))
        res = tracker.update(Decimal("10000.00"), Decimal("10000.00"))
        assert res.equity_drawdown_percent == Decimal("0")
        assert res.within_equity_limit
        assert res.within_balance_limit

    def test_equity_drawdown_percent(self):
        tracker = DrawdownTracker(Decimal("0.10"), Decimal("0.15"))
        # equity drops from 10000 to 9000 -> 10% drawdown
        tracker.update(Decimal("10000.00"), Decimal("10000.00"))
        res = tracker.update(Decimal("9000.00"), Decimal("9000.00"))
        assert res.equity_drawdown_percent == Decimal("10.00")
        assert res.within_equity_limit  # exactly at 10% limit -> within

    def test_equity_drawdown_breach(self):
        tracker = DrawdownTracker(Decimal("0.10"), Decimal("0.15"))
        tracker.update(Decimal("10000.00"), Decimal("10000.00"))
        res = tracker.update(Decimal("8900.00"), Decimal("8900.00"))
        assert res.equity_drawdown_percent == Decimal("11.00")
        assert not res.within_equity_limit
        assert res.limit_breach_reasons

    def test_high_watermark_only_increases(self):
        tracker = DrawdownTracker(Decimal("0.10"), Decimal("0.15"))
        tracker.update(Decimal("10000.00"), Decimal("10000.00"))
        tracker.update(Decimal("11000.00"), Decimal("11000.00"))
        res = tracker.update(Decimal("10500.00"), Decimal("10500.00"))
        assert res.equity_high_watermark == Decimal("11000.00")
        # drawdown from 11000 to 10500 = 4.54%
        assert res.equity_drawdown_percent == Decimal("4.545454545454545454545454545")

    def test_max_drawdown_ever_persisted(self):
        tracker = DrawdownTracker(Decimal("0.10"), Decimal("0.15"))
        tracker.update(Decimal("10000.00"), Decimal("10000.00"))
        tracker.update(Decimal("8000.00"), Decimal("8000.00"))  # 20% DD
        tracker.update(Decimal("12000.00"), Decimal("12000.00"))  # new peak
        res = tracker.update(Decimal("10000.00"), Decimal("10000.00"))
        assert res.max_equity_drawdown_ever == Decimal("20.00")

    def test_persist_and_load_roundtrip(self, tmp_path):
        path = tmp_path / "dd.json"
        tracker = DrawdownTracker(Decimal("0.10"), Decimal("0.15"))
        tracker.update(Decimal("10000.00"), Decimal("10000.00"))
        tracker.update(Decimal("8000.00"), Decimal("8000.00"))
        tracker.persist(str(path))

        loaded = DrawdownTracker.load(
            str(path), Decimal("0.10"), Decimal("0.15")
        )
        assert loaded.state.equity_high_watermark == Decimal("10000.00")
        assert loaded.state.max_equity_drawdown_ever == Decimal("20.00")


class TestDailyPnL:
    def test_net_daily_pnl(self):
        d = DailyPnLState(
            starting_balance=Decimal("10000"),
            starting_equity=Decimal("10000"),
            realized_pnl=Decimal("-500"),
            unrealized_pnl=Decimal("-100"),
        )
        assert d.net_daily_pnl == Decimal("-600")
        assert d.net_daily_pnl_percent == Decimal("-6.00")

    def test_adjusted_starting_reference_deposits(self):
        d = DailyPnLState(
            starting_balance=Decimal("10000"),
            starting_equity=Decimal("10000"),
            deposits=Decimal("2000"),
            withdrawals=Decimal("500"),
        )
        # deposits increase reference, withdrawals decrease
        assert d.adjusted_starting_reference == Decimal("11500")

    def test_daily_loss_limit_breach(self):
        policy = test_policy()
        d = DailyPnLState(
            starting_balance=Decimal("10000"),
            starting_equity=Decimal("10000"),
            realized_pnl=Decimal("-600"),  # 6% > 5% limit
        )
        limit = Decimal("10000") * policy.max_daily_loss_percent
        assert d.net_daily_pnl <= -limit

    def test_deposits_not_treated_as_profit(self):
        d = DailyPnLState(
            starting_balance=Decimal("10000"),
            starting_equity=Decimal("10000"),
            deposits=Decimal("5000"),
            realized_pnl=Decimal("-500"),
        )
        # Net PnL is -500; deposits do not offset it.
        assert d.net_daily_pnl == Decimal("-500")
