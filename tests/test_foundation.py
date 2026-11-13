"""Initial unit tests for the Phase 1 foundation.

Run from the project root:

    python -m pytest tests/ -v
"""

from __future__ import annotations

from decimal import Decimal

from src.broker import MockBrokerAdapter
from src.config import AppConfig, LoggingConfig, RiskConfig, TradingConfig, get_bool
from src.engines import TradeExecutionEngine
from src.execution import TradeExecutionEngineImpl
from src.models import (
    AccountInfo,
    Candle,
    Instrument,
    InstrumentType,
    Order,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Tick,
    TradeResult,
    TradeResultModel,
)


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

def test_get_bool_true_values():
    import os
    os.environ["TEST_BOOL"] = "true"
    assert get_bool("TEST_BOOL") is True
    os.environ["TEST_BOOL"] = "0"
    assert get_bool("TEST_BOOL") is False
    del os.environ["TEST_BOOL"]


def test_config_defaults_live_locked():
    cfg = TradingConfig()
    assert cfg.mode == "simulation"
    assert cfg.enable_live_trading is False
    assert cfg.live_locked is True
    assert cfg.is_live is False


def test_app_config_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "demo")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "false")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DEFAULT_RISK_PER_TRADE", "0.02")
    cfg = AppConfig.from_env()
    assert cfg.trading.mode == "demo"
    assert cfg.trading.live_locked is True
    assert cfg.logging.level == "DEBUG"
    assert cfg.risk.risk_per_trade == 0.02


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

def test_tick_spread_and_mid():
    from datetime import datetime
    tick = Tick(symbol="EURUSD", bid=Decimal("1.0849"), ask=Decimal("1.0851"), timestamp=datetime.now())
    assert tick.spread == Decimal("0.0002")
    assert tick.mid == Decimal("1.0850")


def test_instrument_defaults():
    inst = Instrument(symbol="XAUUSD", name="Gold")
    assert inst.instrument_type == InstrumentType.FOREX
    assert inst.point == Decimal("0.00001")
    assert inst.min_lot == Decimal("0.01")


# ---------------------------------------------------------------------------
# Mock broker tests
# ---------------------------------------------------------------------------

def test_mock_broker_connect_disconnect():
    broker = MockBrokerAdapter()
    assert broker.is_connected is False
    assert broker.connect() is True
    assert broker.is_connected is True
    assert broker.disconnect() is True
    assert broker.is_connected is False


def test_mock_broker_account_info():
    broker = MockBrokerAdapter()
    broker.connect()
    acct = broker.get_account_info()
    assert acct is not None
    assert acct.trade_mode == "demo"
    assert acct.balance == Decimal("10000.0")
    broker.disconnect()


def test_mock_broker_instruments():
    broker = MockBrokerAdapter()
    broker.connect()
    insts = broker.get_instruments()
    symbols = {i.symbol for i in insts}
    assert "XAUUSD" in symbols
    assert "XAGUSD" in symbols
    assert "EURUSD" in symbols
    broker.disconnect()


def test_mock_broker_tick_and_candles():
    broker = MockBrokerAdapter()
    broker.connect()
    tick = broker.get_tick("XAUUSD")
    assert tick is not None
    assert tick.symbol == "XAUUSD"
    assert tick.ask > tick.bid
    candles = broker.get_candles("EURUSD", 5)
    assert len(candles) == 5
    assert all(c.symbol == "EURUSD" for c in candles)
    broker.disconnect()


def test_mock_broker_place_order_simulated():
    broker = MockBrokerAdapter()
    broker.connect()
    request = OrderRequest(
        symbol="EURUSD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=Decimal("0.01"),
        comment="test",
    )
    result = broker.place_order(request)
    assert result.success is True
    assert result.result == TradeResult.SUCCESS
    assert result.ticket is not None
    positions = broker.get_positions()
    assert len(positions) == 1
    broker.disconnect()


def test_mock_broker_close_order():
    broker = MockBrokerAdapter()
    broker.connect()
    request = OrderRequest(
        symbol="EURUSD",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        volume=Decimal("0.05"),
    )
    result = broker.place_order(request)
    ticket = result.ticket
    close_result = broker.close_order(ticket)
    assert close_result.success is True
    positions = broker.get_positions()
    assert len(positions) == 0
    broker.disconnect()


# ---------------------------------------------------------------------------
# Execution engine safety gate tests
# ---------------------------------------------------------------------------

def test_execution_rejects_when_live_locked(monkeypatch):
    from src import config as config_module
    import src.execution as exec_module

    locked_cfg = AppConfig(
        trading=TradingConfig(mode="simulation", enable_live_trading=False),
        logging=LoggingConfig(),
        risk=RiskConfig(),
    )
    # execution.py binds CONFIG by name at import time, so patch that binding.
    monkeypatch.setattr(exec_module, "CONFIG", locked_cfg)
    broker = MockBrokerAdapter()
    engine = TradeExecutionEngineImpl(broker=broker, risk_manager=None)
    request = OrderRequest(
        symbol="EURUSD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=Decimal("0.01"),
    )
    result = engine.execute(request)
    assert result.success is False
    assert result.result == TradeResult.REJECTED
    assert result.error_code == 403


def test_execution_engine_is_an_interface():
    assert issubclass(TradeExecutionEngineImpl, TradeExecutionEngine)
