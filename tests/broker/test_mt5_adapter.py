"""Unit tests for MT5 Broker Adapter (mocked).

Run from the project root:

    python -m pytest tests/broker/test_mt5_adapter.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.broker.mt5.mt5_adapter import MT5BrokerAdapter
from src.broker.mt5.exceptions import (
    MT5InitializationError,
    MT5LiveAccountError,
    MT5NotInstalledError,
    MT5TerminalNotFoundError,
)
from src.models import AccountInfo, TradeResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_mt5_module():
    """Create a mock MT5 module."""
    mt5 = MagicMock()
    mt5.__version__ = "5.0.45"
    return mt5


@pytest.fixture
def mock_terminal_info():
    """Create mock terminal info."""
    info = MagicMock()
    info.version = "5.00"
    info.build = 3500
    info.name = "MetaTrader 5"
    info.company = "MetaQuotes"
    return info


@pytest.fixture
def mock_account_info_demo():
    """Create mock demo account info."""
    info = MagicMock()
    info.login = 123456
    info.name = "Demo User"
    info.server = "PUPrime-Demo"
    info.currency = "USD"
    info.balance = 10000.0
    info.equity = 10000.0
    info.margin = 0.0
    info.free_margin = 10000.0
    info.margin_level = 0.0
    info.trade_allowed = True
    info.trade_mode = 0  # 0 = demo
    return info


@pytest.fixture
def mock_account_info_live():
    """Create mock REAL/live account info (trade_mode == 2)."""
    info = MagicMock()
    info.login = 123456
    info.name = "Live User"
    info.server = "PUPrime-Live"
    info.currency = "USD"
    info.balance = 10000.0
    info.equity = 10000.0
    info.margin = 0.0
    info.free_margin = 10000.0
    info.margin_level = 0.0
    info.trade_allowed = True
    info.trade_mode = 2  # ACCOUNT_TRADE_MODE_REAL
    return info


@pytest.fixture
def mock_account_info_contest():
    """Create mock CONTEST account info (trade_mode == 1)."""
    info = MagicMock()
    info.login = 123456
    info.name = "Contest User"
    info.server = "PUPrime-Contest"
    info.currency = "USD"
    info.balance = 10000.0
    info.equity = 10000.0
    info.margin = 0.0
    info.free_margin = 10000.0
    info.margin_level = 0.0
    info.trade_allowed = True
    info.trade_mode = 1  # ACCOUNT_TRADE_MODE_CONTEST
    return info


@pytest.fixture
def mock_symbols():
    """Create mock symbol list."""
    symbols = []
    for name in ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100"]:
        sym = MagicMock()
        sym.name = name
        sym.description = f"{name} Description"
        sym.currency_base = "XAU" if "XAU" in name else ("XAG" if "XAG" in name else "EUR")
        sym.currency_profit = "USD"
        sym.digits = 2 if "XAU" in name else (3 if "XAG" in name else 5)
        sym.point = 0.01 if "XAU" in name else (0.001 if "XAG" in name else 0.00001)
        sym.trade_tick_size = 0.01 if "XAU" in name else (0.001 if "XAG" in name else 0.00001)
        sym.trade_tick_value = 1.0
        sym.trade_contract_size = 100.0 if "XAU" in name else (5000.0 if "XAG" in name else 100000.0)
        sym.volume_min = 0.01
        sym.volume_max = 100.0
        sym.volume_step = 0.01
        sym.trade_mode = 4  # full access
        sym.swap_long = -1.0
        sym.swap_short = -1.0
        sym.session_volume = 0
        sym.spread = 20
        sym.margin_initial = 0.0
        sym.margin_maintenance = 0.0
        # Metals live under a Metals path; forex under Forex; indices under Indices.
        if "XAU" in name or "XAG" in name:
            sym.path = "\\Metals\\Spot"
        elif "NAS" in name:
            sym.path = "\\Indices\\Cash"
        else:
            sym.path = "\\Forex\\Majors"
        symbols.append(sym)
    return symbols


# ---------------------------------------------------------------------------
# Tests: MT5BrokerAdapter
# ---------------------------------------------------------------------------

class TestMT5BrokerAdapter:
    """Tests for MT5BrokerAdapter using mocked MT5 module."""

    @patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._import_mt5')
    def test_connect_success_demo_account(
        self,
        mock_import,
        mock_mt5_module,
        mock_terminal_info,
        mock_account_info_demo,
        mock_symbols,
    ):
        """Test successful connection with demo account."""
        # Setup mocks
        mock_import.return_value = None
        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols

        with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
            adapter = MT5BrokerAdapter(canonical_symbols=["XAUUSD", "EURUSD", "NAS100"])
            adapter._connection._mt5_module = mock_mt5_module
            adapter._connection._initialized = True

            result = adapter.connect()

        assert result is True
        assert adapter.is_connected is True
        assert adapter._account_info.is_demo_account() is True

    @patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._import_mt5')
    def test_connect_rejects_live_account(
        self,
        mock_import,
        mock_mt5_module,
        mock_terminal_info,
        mock_account_info_live,
        mock_symbols,
    ):
        """Test that live account is rejected."""
        mock_import.return_value = None
        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_live
        mock_mt5_module.symbols_get.return_value = mock_symbols

        with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
            adapter = MT5BrokerAdapter()
            adapter._connection._mt5_module = mock_mt5_module
            adapter._connection._initialized = True

            with pytest.raises(MT5LiveAccountError):
                adapter.connect()

    @patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._import_mt5')
    def test_connect_rejects_contest_account(
        self,
        mock_import,
        mock_mt5_module,
        mock_terminal_info,
        mock_account_info_contest,
        mock_symbols,
    ):
        """Contest accounts (trade_mode == 1) must be rejected."""
        mock_import.return_value = None
        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_contest
        mock_mt5_module.symbols_get.return_value = mock_symbols

        with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
            adapter = MT5BrokerAdapter()
            adapter._connection._mt5_module = mock_mt5_module
            adapter._connection._initialized = True

            with pytest.raises(MT5LiveAccountError):
                adapter.connect()

    @patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._import_mt5')
    def test_connect_missing_account_info_fails_safely(
        self,
        mock_import,
        mock_mt5_module,
        mock_terminal_info,
        mock_symbols,
    ):
        """Missing account information must fail safely (no market data)."""
        from src.broker.mt5.exceptions import MT5AccountError

        mock_import.return_value = None
        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = None  # no account info

        with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
            adapter = MT5BrokerAdapter()
            adapter._connection._mt5_module = mock_mt5_module
            adapter._connection._initialized = True

            with pytest.raises(MT5AccountError):
                adapter.connect()

        # No market data retrieval may occur without a verified demo account.
        adapter._market_data is None
        mock_mt5_module.symbol_info_tick.assert_not_called()
        mock_mt5_module.copy_rates_range.assert_not_called()

    def test_connect_mt5_not_installed(self):
        """Test MT5 not installed error."""
        adapter = MT5BrokerAdapter()
        # Mock the connection manager to raise the right exception
        with patch.object(adapter._connection, '_import_mt5', side_effect=MT5NotInstalledError("MT5 not installed")):
            with pytest.raises(MT5NotInstalledError):
                adapter.connect()

    def test_get_account_info_safe(self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols):
        """Test account info retrieval without sensitive data."""
        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols

        with patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                adapter = MT5BrokerAdapter()
                adapter._connection._mt5_module = mock_mt5_module
                adapter._connection._initialized = True
                adapter.connect()

                account = adapter.get_account_info()

        assert account is not None
        assert isinstance(account, AccountInfo)
        assert account.trade_mode == "demo"
        assert account.currency == "USD"
        assert account.server == "PUPrime-Demo"
        assert account.login == 123456

    def test_get_instruments(self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols):
        """Test instrument list retrieval."""
        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols

        with patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                adapter = MT5BrokerAdapter(canonical_symbols=["XAUUSD", "EURUSD"])
                adapter._connection._mt5_module = mock_mt5_module
                adapter._connection._initialized = True
                adapter.connect()

                instruments = adapter.get_instruments()

        assert len(instruments) >= 2
        symbols = {i.symbol for i in instruments}
        assert "XAUUSD" in symbols
        assert "EURUSD" in symbols

    def test_get_tick(self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols):
        """Test tick retrieval."""
        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols

        # Mock symbol_info_tick
        tick = MagicMock()
        tick.time = int(datetime.now(timezone.utc).timestamp())
        tick.bid = 2000.0
        tick.ask = 2000.02
        tick.last = 2000.01
        tick.volume = 100
        mock_mt5_module.symbol_info_tick.return_value = tick

        with patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                adapter = MT5BrokerAdapter(canonical_symbols=["XAUUSD"])
                adapter._connection._mt5_module = mock_mt5_module
                adapter._connection._initialized = True
                adapter.connect()

                quote = adapter.get_tick("XAUUSD")

        assert quote is not None
        assert quote.symbol == "XAUUSD"
        assert quote.bid == Decimal("2000.0")
        assert quote.ask == Decimal("2000.02")

    def test_place_order_disabled(self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols):
        """Test that order placement is disabled (read-only)."""
        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols

        with patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                adapter = MT5BrokerAdapter()
                adapter._connection._mt5_module = mock_mt5_module
                adapter._connection._initialized = True
                adapter.connect()

                from src.models import OrderRequest, OrderSide, OrderType
                request = OrderRequest(
                    symbol="XAUUSD",
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    volume=Decimal("0.01"),
                )
                result = adapter.place_order(request)

        assert result.success is False
        assert result.result == TradeResult.REJECTED
        assert result.error_code == 403
        assert "READ-ONLY" in result.error_message

    def test_close_order_disabled(self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols):
        """Test that order closing is disabled."""
        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols

        with patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                adapter = MT5BrokerAdapter()
                adapter._connection._mt5_module = mock_mt5_module
                adapter._connection._initialized = True
                adapter.connect()

                result = adapter.close_order("12345")

        assert result.success is False
        assert result.result == TradeResult.REJECTED
        assert result.error_code == 403

    def test_get_orders_empty(self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols):
        """Test that get_orders returns an empty list when the broker reports none."""
        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols
        mock_mt5_module.orders_get.return_value = None

        with patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                adapter = MT5BrokerAdapter()
                adapter._connection._mt5_module = mock_mt5_module
                adapter._connection._initialized = True
                adapter.connect()

                orders = adapter.get_orders()

        assert orders == []
        # Read-only: the terminal must never be asked to send/check orders.
        mock_mt5_module.order_send.assert_not_called()
        mock_mt5_module.order_check.assert_not_called()

    def test_get_positions_empty(self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols):
        """Test that get_positions returns an empty list when the broker reports none."""
        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols
        mock_mt5_module.positions_get.return_value = None

        with patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                adapter = MT5BrokerAdapter()
                adapter._connection._mt5_module = mock_mt5_module
                adapter._connection._initialized = True
                adapter.connect()

                positions = adapter.get_positions()

        assert positions == []
        mock_mt5_module.order_send.assert_not_called()
        mock_mt5_module.order_check.assert_not_called()

    def test_get_orders_readonly_retrieval(self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols):
        """Test genuine read-only retrieval of open/pending orders."""
        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols

        order = MagicMock()
        order.ticket = 5001
        order.symbol = "XAUUSD"
        order.type = 0  # ORDER_TYPE_BUY -> MARKET/BUY
        order.volume_current = 0.10
        order.volume_initial = 0.10
        order.price_open = 2000.0
        order.sl = 1990.0
        order.tp = 2020.0
        order.time_setup = int(datetime.now(timezone.utc).timestamp())
        order.state = 1  # ORDER_STATE_PLACED -> OPEN
        order.comment = "audit-test"
        order.magic = 777
        mock_mt5_module.orders_get.return_value = [order]

        with patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                adapter = MT5BrokerAdapter()
                adapter._connection._mt5_module = mock_mt5_module
                adapter._connection._initialized = True
                adapter.connect()

                orders = adapter.get_orders()

        assert len(orders) == 1
        o = orders[0]
        assert o.ticket == "5001"
        assert o.symbol == "XAUUSD"
        assert o.side.value == "buy"
        assert o.order_type.value == "market"
        assert o.volume == Decimal("0.10")
        assert o.status.value == "open"
        assert o.price == Decimal("2000.0")
        assert o.stop_loss == Decimal("1990.0")
        assert o.take_profit == Decimal("2020.0")
        assert o.magic_number == 777
        # Read-only: no order_send/order_check during retrieval.
        mock_mt5_module.order_send.assert_not_called()
        mock_mt5_module.order_check.assert_not_called()

    def test_get_positions_readonly_retrieval(self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols):
        """Test genuine read-only retrieval of open positions."""
        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols

        pos = MagicMock()
        pos.ticket = 9001
        pos.symbol = "EURUSD"
        pos.type = 1  # POSITION_TYPE_SELL
        pos.volume = 0.50
        pos.price_open = 1.0900
        pos.price_current = 1.0880
        pos.sl = 1.0950
        pos.tp = 1.0800
        pos.profit = 100.0
        pos.time = int(datetime.now(timezone.utc).timestamp())
        pos.comment = "pos-test"
        pos.magic = 888
        mock_mt5_module.positions_get.return_value = [pos]

        with patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                adapter = MT5BrokerAdapter()
                adapter._connection._mt5_module = mock_mt5_module
                adapter._connection._initialized = True
                adapter.connect()

                positions = adapter.get_positions()

        assert len(positions) == 1
        p = positions[0]
        assert p.ticket == "9001"
        assert p.symbol == "EURUSD"
        assert p.side.value == "sell"
        assert p.volume == Decimal("0.50")
        assert p.open_price == Decimal("1.0900")
        assert p.current_price == Decimal("1.0880")
        assert p.profit == Decimal("100.0")
        mock_mt5_module.order_send.assert_not_called()
        mock_mt5_module.order_check.assert_not_called()

    def test_get_candles_bridge_fails_explicitly(self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols):
        """The Phase 1 get_candles bridge must fail explicitly (no silent M1)."""
        from src.broker.mt5.exceptions import MT5DataError

        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols

        with patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                adapter = MT5BrokerAdapter()
                adapter._connection._mt5_module = mock_mt5_module
                adapter._connection._initialized = True
                adapter.connect()

                with pytest.raises(MT5DataError):
                    adapter.get_candles("XAUUSD", 10)

    def test_no_login_ever_called(self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols):
        """The adapter must never call mt5.login() (no account switching / live login)."""
        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols

        tick = MagicMock()
        tick.time = int(datetime.now(timezone.utc).timestamp())
        tick.bid = 2000.0
        tick.ask = 2000.02
        tick.last = 2000.01
        tick.volume = 100
        mock_mt5_module.symbol_info_tick.return_value = tick
        mock_mt5_module.orders_get.return_value = None
        mock_mt5_module.positions_get.return_value = None

        with patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                adapter = MT5BrokerAdapter()
                adapter._connection._mt5_module = mock_mt5_module
                adapter._connection._initialized = True
                adapter.connect()

                # Exercise read-only surface.
                adapter.get_orders()
                adapter.get_positions()
                adapter.get_instruments()
                adapter.get_tick("XAUUSD")

        mock_mt5_module.login.assert_not_called()
        mock_mt5_module.order_send.assert_not_called()
        mock_mt5_module.order_check.assert_not_called()

    def test_disconnect(self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols):
        """Test graceful disconnection."""
        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols
        mock_mt5_module.shutdown.return_value = None

        with patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                adapter = MT5BrokerAdapter()
                adapter._connection._mt5_module = mock_mt5_module
                adapter._connection._initialized = True
                adapter.connect()

                result = adapter.disconnect()

        assert result is True
        assert adapter.is_connected is False
        mock_mt5_module.shutdown.assert_called_once()

    def test_get_discovery_report(self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols):
        """Test discovery report generation."""
        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols

        with patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                adapter = MT5BrokerAdapter(canonical_symbols=["XAUUSD", "EURUSD"])
                adapter._connection._mt5_module = mock_mt5_module
                adapter._connection._initialized = True
                adapter.connect()

                report = adapter.get_discovery_report()

        assert "MT5 Symbol Discovery Report" in report
        assert "XAUUSD" in report
        assert "EURUSD" in report

    def test_run_diagnostics(self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols):
        """Test diagnostics output."""
        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols

        with patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.mt5_adapter.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                adapter = MT5BrokerAdapter()
                adapter._connection._mt5_module = mock_mt5_module
                adapter._connection._initialized = True
                adapter.connect()

                diag = adapter.run_diagnostics()

        assert diag["status"] == "connected"
        assert diag["account_mode"] == "demo"
        assert diag["discovered_symbols"] >= 6
        assert "XAUUSD" in str(diag["symbol_mapping"])


# ---------------------------------------------------------------------------
# Tests: MT5ConnectionManager
# ---------------------------------------------------------------------------

class TestMT5ConnectionManager:
    """Tests for MT5ConnectionManager."""

    def test_import_mt5_not_installed(self):
        """Test import error when MT5 not installed."""
        from src.broker.mt5.connection import MT5ConnectionManager
        from src.broker.mt5.exceptions import MT5NotInstalledError

        manager = MT5ConnectionManager()
        with patch.object(manager, '_import_mt5', side_effect=MT5NotInstalledError("Not installed")):
            with pytest.raises(MT5NotInstalledError):
                manager._import_mt5()

    @patch('os.path.isfile', return_value=True)
    @patch('src.broker.mt5.connection.MT5ConnectionManager.detect_running_terminal', return_value={'pid': 1234, 'name': 'terminal64.exe', 'exe': 'C:\\MT5\\terminal64.exe', 'username': 'user'})
    @patch('src.broker.mt5.connection.MT5ConnectionManager._import_mt5')
    @patch('src.broker.mt5.connection.MT5ConnectionManager._discover_terminal')
    def test_initialize_success(self, mock_discover, mock_import, mock_running, mock_isfile, mock_mt5_module, mock_terminal_info):
        """Test successful initialization."""
        from src.broker.mt5.connection import MT5ConnectionManager

        mock_import.return_value = None
        mock_discover.return_value = "C:\\MT5\\terminal64.exe"
        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info

        manager = MT5ConnectionManager()
        manager._mt5_module = mock_mt5_module

        result = manager.initialize()

        assert result is True
        assert manager.is_initialized is True
        assert manager.terminal_info is not None
        assert manager.terminal_info.version == "5.00"

    @patch('os.path.isfile', return_value=True)
    @patch('src.broker.mt5.connection.MT5ConnectionManager.detect_running_terminal', return_value={'pid': 1234, 'name': 'terminal64.exe', 'exe': 'C:\\MT5\\terminal64.exe', 'username': 'user'})
    @patch('src.broker.mt5.connection.MT5ConnectionManager._import_mt5')
    @patch('src.broker.mt5.connection.MT5ConnectionManager._discover_terminal')
    def test_initialize_failure(self, mock_discover, mock_import, mock_running, mock_isfile, mock_mt5_module):
        """Test initialization failure."""
        from src.broker.mt5.connection import MT5ConnectionManager
        from src.broker.mt5.exceptions import MT5InitializationError

        mock_import.return_value = None
        mock_discover.return_value = "C:\\MT5\\terminal64.exe"
        mock_mt5_module.initialize.return_value = False
        mock_mt5_module.last_error.return_value = (1, "Terminal not found")

        manager = MT5ConnectionManager()
        manager._mt5_module = mock_mt5_module

        with pytest.raises(MT5InitializationError):
            manager.initialize()

    def test_check_connection(self, mock_mt5_module, mock_terminal_info):
        """Test connection health check."""
        from src.broker.mt5.connection import MT5ConnectionManager

        mock_mt5_module.terminal_info.return_value = mock_terminal_info

        manager = MT5ConnectionManager()
        manager._mt5_module = mock_mt5_module
        manager._initialized = True

        assert manager.check_connection() is True
        mock_mt5_module.terminal_info.assert_called()


# ---------------------------------------------------------------------------
# Tests: MT5SymbolDiscovery
# ---------------------------------------------------------------------------

class TestMT5SymbolDiscovery:
    """Tests for MT5SymbolDiscovery."""

    def test_discover_symbols(self, mock_mt5_module, mock_symbols):
        """Test symbol discovery."""
        from src.broker.mt5.symbol_discovery import MT5SymbolDiscovery

        mock_mt5_module.symbols_get.return_value = mock_symbols

        discovery = MT5SymbolDiscovery(mock_mt5_module)
        symbols = discovery.discover_symbols()

        assert len(symbols) == 6
        names = {s.name for s in symbols}
        assert "XAUUSD" in names
        assert "EURUSD" in names

    def test_find_broker_symbol(self, mock_mt5_module, mock_symbols):
        """Test broker symbol lookup."""
        from src.broker.mt5.symbol_discovery import MT5SymbolDiscovery

        mock_mt5_module.symbols_get.return_value = mock_symbols

        discovery = MT5SymbolDiscovery(mock_mt5_module)
        discovery.discover_symbols()

        matches = discovery.find_broker_symbol("XAUUSD")
        assert "XAUUSD" in matches

    def test_auto_map_symbols(self, mock_mt5_module, mock_symbols):
        """Test automatic symbol mapping."""
        from src.broker.mt5.symbol_discovery import MT5SymbolDiscovery

        mock_mt5_module.symbols_get.return_value = mock_symbols

        discovery = MT5SymbolDiscovery(mock_mt5_module)
        mappings = discovery.auto_map_symbols(["XAUUSD", "EURUSD", "NONEXISTENT"])

        assert len(mappings) == 2
        assert mappings[0].canonical_symbol == "XAUUSD"
        assert mappings[1].canonical_symbol == "EURUSD"

    def test_to_instrument_spec(self, mock_mt5_module, mock_symbols):
        """Test conversion to InstrumentSpec."""
        from src.broker.mt5.symbol_discovery import MT5SymbolDiscovery

        mock_mt5_module.symbols_get.return_value = mock_symbols

        discovery = MT5SymbolDiscovery(mock_mt5_module)
        discovery.discover_symbols()

        mt5_info = discovery.get_symbol_info("XAUUSD")
        spec = discovery.to_instrument_spec("XAUUSD", "XAUUSD", mt5_info)

        assert spec.canonical_symbol == "XAUUSD"
        assert spec.instrument_type.value == "metal"
        assert spec.contract_size == 100


# ---------------------------------------------------------------------------
# Tests: MT5MarketData
# ---------------------------------------------------------------------------

class TestMT5MarketData:
    """Tests for MT5MarketData."""

    def test_get_quote(self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols):
        """Test quote retrieval."""
        from src.broker.mt5.connection import MT5ConnectionManager
        from src.broker.mt5.market_data import MT5MarketData

        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols

        # Mock tick
        tick = MagicMock()
        tick.time = int(datetime.now(timezone.utc).timestamp())
        tick.bid = 1.0850
        tick.ask = 1.0852
        tick.last = 1.0851
        tick.volume = 1000
        mock_mt5_module.symbol_info_tick.return_value = tick

        with patch('src.broker.mt5.connection.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.connection.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                conn = MT5ConnectionManager()
                conn._mt5_module = mock_mt5_module
                conn._initialized = True

                market_data = MT5MarketData(conn, {"EURUSD": "EURUSD"})
                quote = market_data.get_quote("EURUSD")

        assert quote is not None
        assert quote.symbol == "EURUSD"
        assert quote.bid == Decimal("1.0850")
        assert quote.ask == Decimal("1.0852")
        assert quote.spread == Decimal("0.0002")

    def test_get_candles(self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols):
        """Test candle retrieval."""
        from src.broker.mt5.connection import MT5ConnectionManager
        from src.broker.mt5.market_data import MT5MarketData
        from src.market_data.models import MarketTimeframe

        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols

        # Mock rates
        now = int(datetime.now(timezone.utc).timestamp())
        rates = [
            {'time': now - 120, 'open': 1.0850, 'high': 1.0855, 'low': 1.0845, 'close': 1.0852,
             'tick_volume': 100, 'real_volume': 1000, 'spread': 2},
            {'time': now - 60, 'open': 1.0852, 'high': 1.0858, 'low': 1.0848, 'close': 1.0855,
             'tick_volume': 110, 'real_volume': 1100, 'spread': 2},
            {'time': now, 'open': 1.0855, 'high': 1.0860, 'low': 1.0850, 'close': 1.0858,
             'tick_volume': 120, 'real_volume': 1200, 'spread': 2},  # current forming
        ]
        mock_mt5_module.copy_rates_range.return_value = rates

        with patch('src.broker.mt5.connection.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.connection.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                conn = MT5ConnectionManager()
                conn._mt5_module = mock_mt5_module
                conn._initialized = True

                market_data = MT5MarketData(conn, {"EURUSD": "EURUSD"})
                bars = market_data.get_candles(
                    "EURUSD",
                    MarketTimeframe.M1,
                    datetime.fromtimestamp(now - 180, tz=timezone.utc),
                    datetime.fromtimestamp(now + 60, tz=timezone.utc),
                    completed_only=True,
                )

        # Should get 2 completed bars (skip position 0 current forming)
        assert len(bars) == 2
        assert all(b.is_complete for b in bars)
        assert all(b.data_source.value == "live" for b in bars)

    def test_get_latest_candle_completed(self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols):
        """Test latest completed candle retrieval."""
        from src.broker.mt5.connection import MT5ConnectionManager
        from src.broker.mt5.market_data import MT5MarketData
        from src.market_data.models import MarketTimeframe

        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols

        now = int(datetime.now(timezone.utc).timestamp())
        rates = [
            {'time': now, 'open': 1.0855, 'high': 1.0860, 'low': 1.0850, 'close': 1.0858,
             'tick_volume': 120, 'real_volume': 1200, 'spread': 2},  # current forming
            {'time': now - 60, 'open': 1.0852, 'high': 1.0858, 'low': 1.0848, 'close': 1.0855,
             'tick_volume': 110, 'real_volume': 1100, 'spread': 2},  # last completed
        ]
        mock_mt5_module.copy_rates_from_pos.return_value = rates

        with patch('src.broker.mt5.connection.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.connection.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                conn = MT5ConnectionManager()
                conn._mt5_module = mock_mt5_module
                conn._initialized = True

                market_data = MT5MarketData(conn, {"EURUSD": "EURUSD"})
                bar = market_data.get_latest_candle("EURUSD", MarketTimeframe.M1, completed_only=True)

        assert bar is not None
        assert bar.is_complete is True
        assert bar.close == Decimal("1.0855")  # last completed close

    def test_get_latest_candle_incomplete(self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols):
        """Test latest incomplete candle retrieval."""
        from src.broker.mt5.connection import MT5ConnectionManager
        from src.broker.mt5.market_data import MT5MarketData
        from src.market_data.models import MarketTimeframe

        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols

        now = int(datetime.now(timezone.utc).timestamp())
        rates = [
            {'time': now, 'open': 1.0855, 'high': 1.0860, 'low': 1.0850, 'close': 1.0858,
             'tick_volume': 120, 'real_volume': 1200, 'spread': 2},  # current forming
        ]
        mock_mt5_module.copy_rates_from_pos.return_value = rates

        with patch('src.broker.mt5.connection.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.connection.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                conn = MT5ConnectionManager()
                conn._mt5_module = mock_mt5_module
                conn._initialized = True

                market_data = MT5MarketData(conn, {"EURUSD": "EURUSD"})
                bar = market_data.get_latest_candle("EURUSD", MarketTimeframe.M1, completed_only=False)

        assert bar is not None
        assert bar.is_complete is False

    def test_timeframe_conversion_all_timeframes(self):
        """Every requested timeframe must map to the correct MT5 constant."""
        from src.broker.mt5.market_data import MT5MarketData, MT5_TIMEFRAME_MAP
        from src.market_data.models import MarketTimeframe

        expected = {
            MarketTimeframe.M1: 1,
            MarketTimeframe.M5: 5,
            MarketTimeframe.M15: 15,
            MarketTimeframe.M30: 30,
            MarketTimeframe.H1: 60,
            MarketTimeframe.H4: 240,
            MarketTimeframe.D1: 1440,
        }
        md = MT5MarketData.__new__(MT5MarketData)  # no connection needed
        for tf, constant in expected.items():
            assert md._convert_timeframe(tf) == constant, f"{tf} mapped incorrectly"
            assert MT5_TIMEFRAME_MAP[tf] == constant

    def test_get_candles_passes_correct_timeframe_and_preserves_fields(
        self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols
    ):
        """get_candles must request the exact timeframe and preserve all fields."""
        from src.broker.mt5.connection import MT5ConnectionManager
        from src.broker.mt5.market_data import MT5MarketData
        from src.market_data.models import MarketTimeframe, DataSource

        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols

        now = int(datetime.now(timezone.utc).timestamp())
        h1 = 3600
        rates = [
            {'time': now - 2 * h1, 'open': 1.1000, 'high': 1.1010, 'low': 1.0990, 'close': 1.1005,
             'tick_volume': 100, 'real_volume': 1000, 'spread': 2},
            {'time': now - h1, 'open': 1.1005, 'high': 1.1015, 'low': 1.1000, 'close': 1.1010,
             'tick_volume': 110, 'real_volume': 1100, 'spread': 2},
        ]
        mock_mt5_module.copy_rates_range.return_value = rates

        with patch('src.broker.mt5.connection.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.connection.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                conn = MT5ConnectionManager()
                conn._mt5_module = mock_mt5_module
                conn._initialized = True

                market_data = MT5MarketData(conn, {"EURUSD": "EURUSD"})
                bars = market_data.get_candles(
                    "EURUSD",
                    MarketTimeframe.H1,
                    datetime.fromtimestamp(now - 3 * h1, tz=timezone.utc),
                    datetime.fromtimestamp(now, tz=timezone.utc),
                    completed_only=True,
                )

        # H1 (60) must be passed to copy_rates_range, never M1 (1).
        args = mock_mt5_module.copy_rates_range.call_args[0]
        assert args[1] == 60, f"Expected H1 constant 60, got {args[1]}"

        assert len(bars) == 2
        b = bars[0]
        assert b.timeframe == MarketTimeframe.H1
        assert b.open == Decimal("1.1000")
        assert b.high == Decimal("1.1010")
        assert b.low == Decimal("1.0990")
        assert b.close == Decimal("1.1005")
        assert b.tick_volume == 100
        assert b.real_volume == 1000
        assert b.spread == 2
        assert b.is_complete is True
        assert b.data_source == DataSource.LIVE
        assert b.timestamp.tzinfo is not None
        assert b.timestamp.utcoffset() == timedelta(0)

class TestMT5MarketDataProvider:
    """Tests for MT5MarketDataProvider."""

    def test_provider_interface(self, mock_mt5_module, mock_terminal_info, mock_account_info_demo, mock_symbols):
        """Test that MT5MarketDataProvider implements MarketDataProvider."""
        from src.broker.mt5.mt5_adapter import MT5BrokerAdapter
        from src.market_data.mt5_provider import MT5MarketDataProvider
        from src.market_data.models import MarketTimeframe

        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.account_info.return_value = mock_account_info_demo
        mock_mt5_module.symbols_get.return_value = mock_symbols

        tick = MagicMock()
        tick.time = int(datetime.now(timezone.utc).timestamp())
        tick.bid = 1.0850
        tick.ask = 1.0852
        tick.last = 1.0851
        tick.volume = 1000
        mock_mt5_module.symbol_info_tick.return_value = tick

        now = int(datetime.now(timezone.utc).timestamp())
        rates = [
            {'time': now - 60, 'open': 1.0850, 'high': 1.0855, 'low': 1.0845, 'close': 1.0852,
             'tick_volume': 100, 'real_volume': 1000, 'spread': 2},
            {'time': now, 'open': 1.0852, 'high': 1.0858, 'low': 1.0848, 'close': 1.0855,
             'tick_volume': 110, 'real_volume': 1100, 'spread': 2},
        ]
        mock_mt5_module.copy_rates_range.return_value = rates
        mock_mt5_module.copy_rates_from_pos.return_value = rates

        with patch('src.broker.mt5.connection.MT5ConnectionManager._import_mt5', return_value=None):
            with patch('os.path.isfile', return_value=True), patch('src.broker.mt5.connection.MT5ConnectionManager._discover_terminal', return_value="C:\\MT5\\terminal64.exe"):
                adapter = MT5BrokerAdapter(canonical_symbols=["EURUSD"])
                adapter._connection._mt5_module = mock_mt5_module
                adapter._connection._initialized = True
                adapter.connect()

                provider = MT5MarketDataProvider(adapter)

                # Test interface methods
                assert provider.name == "MT5 (PU Prime Demo)"
                assert provider.is_connected is True
                assert provider.is_simulated is False

                symbols = provider.get_symbols()
                assert len(symbols) >= 1

                timeframes = provider.get_timeframes()
                assert MarketTimeframe.M1 in timeframes
                assert MarketTimeframe.H1 in timeframes

                quote = provider.get_quote("EURUSD")
                assert quote is not None

                bars = provider.get_candles("EURUSD", MarketTimeframe.M1,
                    datetime.fromtimestamp(now - 120, tz=timezone.utc),
                    datetime.fromtimestamp(now, tz=timezone.utc))
                assert len(bars) >= 1

                latest = provider.get_latest_candle("EURUSD", MarketTimeframe.M1)
                assert latest is not None


# ---------------------------------------------------------------------------
# Tests: IPC and connection resilience (additional audit tests)
# ---------------------------------------------------------------------------

class TestMT5IPCAndResilience:
    """Tests for IPC failure handling, incorrect paths, and reconnection."""

    def test_incorrect_terminal_path_raises_not_found(self):
        """An incorrect terminal path must raise MT5TerminalNotFoundError."""
        from src.broker.mt5.connection import MT5ConnectionManager

        manager = MT5ConnectionManager(terminal_path="C:\\Nonexistent\\terminal64.exe")
        with pytest.raises(MT5TerminalNotFoundError):
            manager.initialize()

    @patch('src.broker.mt5.connection.MT5ConnectionManager._import_mt5')
    @patch('src.broker.mt5.connection.MT5ConnectionManager._discover_terminal')
    @patch('os.path.isfile', return_value=True)
    def test_ipc_timeout_reported_with_error_code(
        self, mock_discover, mock_import, mock_mt5_module,
    ):
        """IPC timeout (-10005) is reported with the exact error code/desc."""
        from src.broker.mt5.connection import MT5ConnectionManager
        from src.broker.mt5.exceptions import MT5InitializationError

        mock_import.return_value = None
        mock_discover.return_value = "C:\\MT5\\terminal64.exe"
        mock_mt5_module.initialize.return_value = False
        mock_mt5_module.last_error.return_value = (-10005, "IPC timeout")

        manager = MT5ConnectionManager()
        manager._mt5_module = mock_mt5_module

        with pytest.raises(MT5InitializationError) as exc_info:
            manager.initialize()

        assert "-10005" in str(exc_info.value)
        assert "IPC timeout" in str(exc_info.value)

    def test_reconnect_after_shutdown(self, mock_mt5_module, mock_terminal_info):
        """Reconnection shuts down and re-initializes without duplicate processes."""
        from src.broker.mt5.connection import MT5ConnectionManager

        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info
        mock_mt5_module.shutdown.return_value = None

        manager = MT5ConnectionManager()

        with patch.object(manager, '_import_mt5') as mock_import, \
             patch.object(manager, '_discover_terminal', return_value="C:\\MT5\\terminal64.exe"), \
             patch('os.path.isfile', return_value=True):

            def _fake_import(*args, **kwargs):
                manager._mt5_module = mock_mt5_module

            mock_import.side_effect = _fake_import
            mock_import.return_value = None

            # First init
            assert manager.initialize() is True
            assert manager.is_initialized

            # Reconnect
            assert manager.reconnect() is True
            assert manager.is_initialized

            # shutdown should have been called between init and reconnect
            mock_mt5_module.shutdown.assert_called()

    @patch('src.broker.mt5.connection.MT5ConnectionManager._import_mt5')
    @patch('src.broker.mt5.connection.MT5ConnectionManager._discover_terminal')
    @patch('os.path.isfile', return_value=True)
    def test_multiple_terminal_instances_uses_first(
        self, mock_discover, mock_import, mock_mt5_module,
    ):
        """When multiple terminals run, the first detected is used."""
        from src.broker.mt5.connection import MT5ConnectionManager

        mock_import.return_value = None
        mock_discover.return_value = "C:\\MT5\\terminal64.exe"
        mock_mt5_module.initialize.return_value = True
        mock_mt5_module.terminal_info.return_value = mock_terminal_info

        # Simulate two running terminals
        with patch(
            'src.broker.mt5.connection.MT5ConnectionManager.detect_running_terminal',
            return_value={'pid': 100, 'name': 'terminal64.exe', 'exe': 'C:\\MT5\\terminal64.exe', 'username': 'user'},
        ):
            manager = MT5ConnectionManager()
            manager._mt5_module = mock_mt5_module
            result = manager.initialize()
            assert result is True

    def test_mt5_not_installed_raises(self):
        """Missing MetaTrader5 package raises MT5NotInstalledError."""
        adapter = MT5BrokerAdapter()
        with patch.object(adapter._connection, '_import_mt5',
                          side_effect=MT5NotInstalledError("Not installed")):
            with pytest.raises(MT5NotInstalledError):
                adapter.connect()

    def test_symbol_discovery_with_dot_s_suffix(self, mock_mt5_module):
        """Broker symbols with .s suffix (e.g. XAUUSD.s) are matched to canonical."""
        from src.broker.mt5.symbol_discovery import MT5SymbolDiscovery

        sym = MagicMock()
        sym.name = "XAUUSD.s"
        sym.description = "Gold vs US Dollar"
        sym.currency_base = "XAU"
        sym.currency_profit = "USD"
        sym.digits = 2
        sym.point = 0.01
        sym.trade_tick_size = 0.01
        sym.trade_tick_value = 1.0
        sym.trade_contract_size = 100.0
        sym.volume_min = 0.01
        sym.volume_max = 100.0
        sym.volume_step = 0.01
        sym.trade_mode = 4
        sym.swap_long = -1.0
        sym.swap_short = -1.0
        sym.session_volume = 0
        sym.spread = 20
        sym.margin_initial = 0.0
        sym.margin_maintenance = 0.0
        sym.path = "\\Metals\\Spot"
        mock_mt5_module.symbols_get.return_value = [sym]

        discovery = MT5SymbolDiscovery(mock_mt5_module)
        discovery.discover_symbols()

        matches = discovery.find_broker_symbol("XAUUSD")
        assert "XAUUSD.s" in matches

    def test_python_package_version_check(self):
        """MetaTrader5 package version is detectable."""
        import MetaTrader5 as mt5
        version = getattr(mt5, "__version__", None)
        assert version is not None
        assert isinstance(version, str)
        print("    MetaTrader5 package version: %s" % version)