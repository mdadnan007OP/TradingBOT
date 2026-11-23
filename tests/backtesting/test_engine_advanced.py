"""Advanced engine tests: multi-symbol, multi-strategy, warmup, look-ahead, news."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from src.backtesting.config import AccountConfig, test_backtest_config
from src.backtesting.data_loader import BacktestDataLoader
from src.backtesting.engine import BacktestEngine
from src.indicators import create_engine
from src.market_data.models import MarketTimeframe
from src.strategies.base import SignalDirection
from src.strategies.manager import StrategyManager
from src.strategies.registry import StrategyRegistry
from tests.backtesting.conftest import BASE, ScriptedStrategy, make_bars, relaxed_risk_policy


def _config(**overrides):
    base = {
        "account": AccountConfig(starting_balance=Decimal("100000"), currency="USD", leverage=Decimal("30")),
        "risk_policy": relaxed_risk_policy(),
    }
    base.update(overrides)
    return test_backtest_config(overrides=base)


def _manager(strategies):
    reg = StrategyRegistry()
    for s in strategies:
        reg.register(s)
    return StrategyManager(indicator_engine=create_engine(), registry=reg)


def test_multi_symbol_backtest():
    eur = make_bars([1.1000] * 40, symbol="EURUSD")
    gbp = make_bars([1.2500] * 40, symbol="GBPUSD")
    data = BacktestDataLoader().from_lists({
        ("EURUSD", MarketTimeframe.H1): eur,
        ("GBPUSD", MarketTimeframe.H1): gbp,
    })
    cfg = _config(symbols=["EURUSD", "GBPUSD"], timeframes=["H1"])
    engine = BacktestEngine(cfg, data, strategy_manager=_manager([ScriptedStrategy({10: SignalDirection.LONG})]))
    result = engine.run()
    # Both symbols should have opened positions → at least 2 trades.
    assert result.total_trades >= 2


def test_multi_strategy_backtest():
    bars = make_bars([1.1000] * 40, symbol="EURUSD")
    data = BacktestDataLoader().from_lists({("EURUSD", MarketTimeframe.H1): bars})
    cfg = _config()
    mgr = _manager([
        ScriptedStrategy({10: SignalDirection.LONG}, name="StratA"),
        ScriptedStrategy({20: SignalDirection.SHORT}, name="StratB"),
    ])
    engine = BacktestEngine(cfg, data, strategy_manager=mgr)
    result = engine.run()
    strategies_used = {t.strategy_name for t in result.trades}
    assert "StratA" in strategies_used
    assert "StratB" in strategies_used


def test_look_ahead_prevention_no_future_bars():
    # A signal at the last bar with next-bar fill cannot fill (no future bar).
    bars = make_bars([1.1000] * 15, symbol="EURUSD")
    data = BacktestDataLoader().from_lists({("EURUSD", MarketTimeframe.H1): bars})
    engine = BacktestEngine(_config(), data, strategy_manager=_manager([ScriptedStrategy({14: SignalDirection.LONG})]))
    result = engine.run()
    assert result.total_trades == 0


def test_warmup_supplies_indicator_history():
    # With enough warmup bars, a strategy can use indicators; the engine must
    # feed the full revealed window (not just the current bar).
    closes = [1.1000 + i * 0.0001 for i in range(60)]
    bars = make_bars(closes, symbol="EURUSD")
    data = BacktestDataLoader().from_lists({("EURUSD", MarketTimeframe.H1): bars})
    engine = BacktestEngine(_config(), data, strategy_manager=_manager([ScriptedStrategy({30: SignalDirection.LONG})]))
    result = engine.run()
    assert result.total_trades >= 1


def test_news_block_prevents_trade():
    from src.news.config import test_news_config
    from src.news.providers.mock_provider import MockCalendarProvider
    from src.news.service import NewsService

    bars = make_bars([1.1000] * 40, symbol="EURUSD")
    data = BacktestDataLoader().from_lists({("EURUSD", MarketTimeframe.H1): bars})

    # Mock provider: NFP (HIGH, USD) at BASE + 600 min = bar index 10's close.
    news = NewsService(
        config=test_news_config(),
        calendar_providers=[MockCalendarProvider(base_time=BASE)],
    )
    news.refresh(BASE, BASE + timedelta(days=2), now=BASE)

    cfg = _config(news_enabled=True)
    engine = BacktestEngine(
        cfg, data, strategy_manager=_manager([ScriptedStrategy({10: SignalDirection.LONG})]),
        news_service=news,
    )
    result = engine.run()
    assert len(result.news_blocks) >= 1
    assert result.total_trades == 0