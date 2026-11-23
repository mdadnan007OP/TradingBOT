"""End-to-end backtesting engine tests."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from src.backtesting.config import test_backtest_config
from src.backtesting.data_loader import BacktestDataLoader
from src.backtesting.engine import BacktestEngine
from src.indicators import create_engine
from src.strategies.base import SignalDirection
from src.strategies.manager import StrategyManager
from src.strategies.registry import StrategyRegistry
from tests.backtesting.conftest import (
    BASE,
    ScriptedStrategy,
    make_bars,
    relaxed_risk_policy,
)


def _build_engine(closes, signals_by_index, config=None, fill_on_next_bar=True):
    bars = make_bars(closes, symbol="EURUSD")
    data = BacktestDataLoader().from_lists({("EURUSD", bars[0].timeframe): bars})

    registry = StrategyRegistry()
    registry.register(ScriptedStrategy(signals_by_index))
    manager = StrategyManager(indicator_engine=create_engine(), registry=registry)

    cfg = config or test_backtest_config(
        overrides={
            "account": __import__("src.backtesting.config", fromlist=["AccountConfig"]).AccountConfig(
                starting_balance=Decimal("100000"), currency="USD", leverage=Decimal("30")
            ),
            "risk_policy": relaxed_risk_policy(),
        }
    )
    engine = BacktestEngine(cfg, data, strategy_manager=manager)
    return engine


def test_engine_runs_and_produces_equity_curve():
    # Flat then a scripted LONG at index 10; close_all at end guarantees a trade.
    closes = [1.1000] * 40
    engine = _build_engine(closes, {10: SignalDirection.LONG})
    result = engine.run()

    assert result.total_trades >= 1
    assert len(result.equity_curve) > 0
    assert result.final_balance is not None


def test_engine_records_events():
    closes = [1.1000] * 40
    engine = _build_engine(closes, {10: SignalDirection.LONG})
    result = engine.run()
    types = {e.event_type.value for e in result.events}
    assert "SIGNAL" in types
    assert "RISK_DECISION" in types


def test_engine_short_signal_opens_short():
    closes = [1.1000] * 40
    engine = _build_engine(closes, {10: SignalDirection.SHORT})
    result = engine.run()
    assert result.total_trades >= 1
    # The single closed trade should be a SHORT.
    assert result.trades[0].side.value == "SHORT"


def test_engine_next_bar_entry_skips_last_bar_signal():
    # Signal on the final bar with next-bar fill → no next bar → no trade.
    closes = [1.1000] * 12
    engine = _build_engine(closes, {11: SignalDirection.LONG})
    result = engine.run()
    assert result.total_trades == 0


def test_engine_same_bar_fill_executes_last_bar_signal():
    closes = [1.1000] * 12
    cfg = test_backtest_config(
        overrides={
            "account": __import__("src.backtesting.config", fromlist=["AccountConfig"]).AccountConfig(
                starting_balance=Decimal("100000"), currency="USD", leverage=Decimal("30")
            ),
            "risk_policy": relaxed_risk_policy(),
        }
    )
    # Turn off next-bar fill via dataclasses.replace on the execution config.
    import dataclasses
    cfg = dataclasses.replace(
        cfg,
        execution=dataclasses.replace(cfg.execution, fill_on_next_bar=False),
    )
    engine = _build_engine(closes, {11: SignalDirection.LONG}, config=cfg)
    result = engine.run()
    # Same-bar fill opens a position on the last bar → closed at end-of-data.
    assert result.total_trades >= 1


def test_engine_no_signal_no_trade():
    closes = [1.1000] * 20
    engine = _build_engine(closes, {})
    result = engine.run()
    assert result.total_trades == 0


def test_engine_multiple_independent_signals():
    closes = [1.1000] * 60
    engine = _build_engine(
        closes,
        {10: SignalDirection.LONG, 30: SignalDirection.SHORT, 45: SignalDirection.LONG},
    )
    result = engine.run()
    assert result.total_trades >= 1