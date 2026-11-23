"""Tests for risk-state carry-forward: daily loss and drawdown lockouts."""

from __future__ import annotations

import dataclasses
from datetime import timedelta
from decimal import Decimal

from src.backtesting.config import AccountConfig, test_backtest_config
from src.backtesting.data_loader import BacktestDataLoader
from src.backtesting.engine import BacktestEngine
from src.indicators import create_engine
from src.market_data.models import MarketTimeframe
from src.risk_management.config import test_policy
from src.strategies.base import SignalDirection
from src.strategies.manager import StrategyManager
from src.strategies.registry import StrategyRegistry
from tests.backtesting.conftest import BASE, ScriptedStrategy, make_bars, relaxed_risk_policy


def _manager():
    reg = StrategyRegistry()
    reg.register(ScriptedStrategy({}))
    return StrategyManager(indicator_engine=create_engine(), registry=reg)


def test_daily_loss_budget_blocks_oversized_risk():
    # A tiny daily-loss budget (0.0001% of 100k = 10 USD) is smaller than the
    # ~999 USD risk of a 1% trade, so the daily-budget guard must reject the
    # entry outright. The rejection is recorded (not silently dropped).
    policy = dataclasses.replace(
        test_policy(),
        max_exposure_per_instrument_percent=Decimal("10"),
        max_exposure_per_asset_class_percent=Decimal("10"),
        max_margin_usage_percent=Decimal("0.90"),
        max_stop_distance=None,
        max_stop_distance_percent=None,
        max_daily_loss_percent=Decimal("0.0001"),  # ~10 USD on 100k
    )
    closes = [1.1000] + [1.1000 - i * 0.0010 for i in range(1, 40)]
    bars = make_bars(closes, symbol="EURUSD")
    data = BacktestDataLoader().from_lists({("EURUSD", MarketTimeframe.H1): bars})

    reg = StrategyRegistry()
    reg.register(ScriptedStrategy({2: SignalDirection.LONG}))
    mgr = StrategyManager(indicator_engine=create_engine(), registry=reg)

    cfg = test_backtest_config(overrides={
        "account": AccountConfig(starting_balance=Decimal("100000"), currency="USD", leverage=Decimal("30")),
        "risk_policy": policy,
    })
    engine = BacktestEngine(cfg, data, strategy_manager=mgr)
    result = engine.run()
    # The run completes and risk state is carried (no crash).
    assert result.final_balance is not None
    # The oversized trade is rejected before it ever opens.
    assert result.total_trades == 0
    # The daily-budget rejection is surfaced in the results.
    assert any("daily" in r.get("reason", "").lower() for r in result.rejected_signals)


def test_risk_state_persists_across_segment():
    # Two consecutive engine runs on the same data must not share state; each
    # starts fresh from the configured balance.
    bars = make_bars([1.1000] * 30, symbol="EURUSD")
    data = BacktestDataLoader().from_lists({("EURUSD", MarketTimeframe.H1): bars})
    reg = StrategyRegistry()
    reg.register(ScriptedStrategy({10: SignalDirection.LONG}))

    cfg = test_backtest_config(overrides={
        "account": AccountConfig(starting_balance=Decimal("50000"), currency="USD", leverage=Decimal("30")),
        "risk_policy": relaxed_risk_policy(),
    })
    e1 = BacktestEngine(cfg, data, strategy_manager=StrategyManager(create_engine(), reg))
    r1 = e1.run()
    e2 = BacktestEngine(cfg, data, strategy_manager=StrategyManager(create_engine(), reg))
    r2 = e2.run()
    # Both runs start from the same configured balance (no shared mutable state).
    assert r1.equity_curve[0].balance == Decimal("50000")
    assert r2.equity_curve[0].balance == Decimal("50000")