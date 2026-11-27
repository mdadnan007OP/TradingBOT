"""MT5 Broker Adapter implementing BrokerAdapter interface."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from src.broker import BrokerAdapter
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
from src.broker.mt5.connection import MT5ConnectionManager, MT5AccountInfo
from src.broker.mt5.symbol_discovery import MT5SymbolDiscovery, SymbolMapping
from src.broker.mt5.market_data import MT5MarketData
from src.broker.mt5.exceptions import (
    MT5AccountError,
    MT5ConnectionError,
    MT5DataError,
    MT5LiveAccountError,
    MT5NotInstalledError,
    MT5SymbolError,
    MT5TerminalNotFoundError,
    MT5TerminalNotRunningError,
)

logger = logging.getLogger(__name__)


class MT5BrokerAdapter(BrokerAdapter):
    """MetaTrader 5 broker adapter for PU Prime demo account.

    Implements read-only market data retrieval and account info.
    Order placement methods are stubbed to enforce demo-only safety.
    """

    def __init__(
        self,
        terminal_path: Optional[str] = None,
        timeout: int = 30,
        portable: bool = False,
        canonical_symbols: Optional[List[str]] = None,
    ) -> None:
        """Initialize MT5 broker adapter.

        Args:
            terminal_path: Optional explicit path to MT5 terminal.
            timeout: Connection timeout in seconds.
            portable: Use portable mode.
            canonical_symbols: List of canonical symbols to map.
        """
        self._terminal_path = terminal_path
        self._timeout = timeout
        self._portable = portable
        self._canonical_symbols = canonical_symbols or [
            "XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY",
            "AUDUSD", "USDCAD", "WTIUSD", "BRENTUSD", "NAS100",
            "US500", "US30", "GER40", "UK100", "BTCUSD", "ETHUSD",
        ]

        self._connection = MT5ConnectionManager(
            terminal_path=terminal_path,
            timeout=timeout,
            portable=portable,
        )
        self._symbol_discovery: Optional[MT5SymbolDiscovery] = None
        self._market_data: Optional[MT5MarketData] = None
        self._account_info: Optional[MT5AccountInfo] = None
        self._symbol_mapping: Dict[str, str] = {}
        self._mappings: List[SymbolMapping] = []
        self._connected = False
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @property
    def name(self) -> str:
        return "MT5BrokerAdapter (PU Prime Demo)"

    @property
    def is_connected(self) -> bool:
        return self._connected and self._connection.check_connection()

    def connect(self) -> bool:
        """Connect to MT5 terminal and validate demo account.

        Demo verification happens BEFORE any symbol discovery or market data
        retrieval. Missing account information, contest accounts, and real/live
        accounts are all refused safely.
        """
        try:
            self._logger.info("Connecting to MT5 terminal...")
            self._connection.initialize()

            # --- DEMO-ONLY SAFETY LOCK (before any data retrieval) ---
            self._account_info = MT5AccountInfo(self._connection._mt5_module)

            if not self._account_info.is_account_available():
                self._connection.shutdown()
                self._connected = False
                raise MT5AccountError(
                    "Account information unavailable; refusing to continue. "
                    "Open MT5, log into your PU Prime DEMO account, then retry."
                )

            if not self._account_info.is_demo_account():
                mode = self._account_info.get_account_mode_str()
                self._logger.error(
                    "%s account detected (trade_mode=%s). Demo-only policy enforced.",
                    mode.upper(),
                    mode,
                )
                self._connection.shutdown()
                self._connected = False
                raise MT5LiveAccountError(
                    f"{mode.upper()} account detected. This adapter only supports "
                    "DEMO accounts for safety; contest and real accounts are rejected."
                )

            self._logger.info("Demo account validated: %s", self._account_info.get_safe_account_summary())

            # Discover symbols (only after demo verification succeeded)
            self._symbol_discovery = MT5SymbolDiscovery(self._connection._mt5_module)
            self._symbol_discovery.discover_symbols()

            # Auto-map canonical symbols
            self._mappings = self._symbol_discovery.auto_map_symbols(self._canonical_symbols)
            self._symbol_mapping = {
                m.canonical_symbol: m.broker_symbol for m in self._mappings
            }

            # Initialize market data retriever
            self._market_data = MT5MarketData(self._connection, self._symbol_mapping)

            self._connected = True
            self._logger.info("MT5 broker adapter connected successfully")
            return True

        except MT5LiveAccountError:
            raise
        except MT5AccountError:
            raise
        except MT5TerminalNotRunningError:
            raise
        except (MT5NotInstalledError, MT5TerminalNotFoundError):
            # Configuration/environment errors must propagate so callers can
            # decide how to handle a missing package or terminal.
            self._connected = False
            raise
        except Exception as exc:
            self._logger.exception("Failed to connect MT5 adapter: %s", exc)
            self._connected = False
            return False

    def disconnect(self) -> bool:
        """Disconnect from MT5 terminal."""
        self._connected = False
        return self._connection.shutdown()

    def get_account_info(self) -> Optional[AccountInfo]:
        """Get current account information (safe, non-sensitive)."""
        if not self.is_connected or self._account_info is None:
            return None

        try:
            info = self._account_info.get_account_info()
            if info is None:
                return None

            return AccountInfo(
                login=getattr(info, 'login', 0),
                name=getattr(info, 'name', 'Demo Account'),
                server=getattr(info, 'server', 'PU Prime Demo'),
                currency=getattr(info, 'currency', 'USD'),
                balance=Decimal(str(getattr(info, 'balance', 0))),
                equity=Decimal(str(getattr(info, 'equity', 0))),
                margin=Decimal(str(getattr(info, 'margin', 0))),
                free_margin=Decimal(str(getattr(info, 'free_margin', 0))),
                margin_level=Decimal(str(getattr(info, 'margin_level', 0))) if getattr(info, 'margin_level', 0) > 0 else None,
                trade_allowed=getattr(info, 'trade_allowed', False),
                trade_mode="demo",  # Always demo due to safety check
            )
        except Exception as exc:
            self._logger.warning("Failed to get account info: %s", exc)
            return None

    def get_instruments(self) -> List[Instrument]:
        """Get list of tradable instruments from MT5."""
        if not self.is_connected or self._symbol_discovery is None:
            return []

        instruments = []
        for mapping in self._mappings:
            mt5_info = self._symbol_discovery.get_symbol_info(mapping.broker_symbol)
            if mt5_info is None:
                continue

            spec = self._symbol_discovery.to_instrument_spec(
                mapping.canonical_symbol,
                mapping.broker_symbol,
                mt5_info,
            )

            instruments.append(Instrument(
                symbol=spec.canonical_symbol,
                name=spec.name,
                instrument_type=spec.instrument_type,
                base_currency=spec.base_currency,
                quote_currency=spec.quote_currency,
                point=spec.tick_size or Decimal("0.00001"),
                min_lot=Decimal(str(mt5_info.volume_min)),
                max_lot=Decimal(str(mt5_info.volume_max)),
                lot_step=Decimal(str(mt5_info.volume_step)),
            ))

        return instruments

    def get_tick(self, symbol: str) -> Optional[Tick]:
        """Get latest tick for a symbol."""
        if not self.is_connected or self._market_data is None:
            return None

        # Map canonical to broker symbol if needed
        broker_symbol = self._symbol_mapping.get(symbol, symbol)
        # Use the canonical symbol for market data (it handles mapping internally)
        quote = self._market_data.get_quote(symbol)
        if quote is None:
            return None

        return Tick(
            symbol=symbol,
            bid=quote.bid,
            ask=quote.ask,
            timestamp=quote.timestamp,
            last=quote.last,
            volume=quote.volume,
        )

    def get_candles(self, symbol: str, count: int) -> List[Candle]:
        """Not supported on the MT5 adapter bridge — fails explicitly.

        The Phase 1 ``BrokerAdapter.get_candles(symbol, count)`` signature
        carries no timeframe, so it cannot honor a requested timeframe and would
        silently return M1 data (mislabeled). To prevent that, this method
        raises :class:`MT5DataError`.

        Use the authoritative, timeframe-aware path instead::

            from src.market_data.mt5_provider import MT5MarketDataProvider
            from src.market_data.service import MarketDataService
            from src.market_data.models import MarketTimeframe

            provider = MT5MarketDataProvider(adapter)
            service = MarketDataService()
            service.register_provider("mt5", provider)
            bars = service.get_candles("XAUUSD", MarketTimeframe.H1, start, end)
        """
        raise MT5DataError(
            "MT5BrokerAdapter.get_candles() does not accept a timeframe and is "
            "disabled to prevent returning mislabeled M1 candles. Use "
            "MT5MarketDataProvider.get_candles(symbol, timeframe, start, end) via "
            "MarketDataService for correct timeframe-aware retrieval."
        )

    # --- Safety-locked order methods (READ-ONLY) ---

    def place_order(self, request: OrderRequest) -> TradeResultModel:
        """Order placement is disabled for demo-only safety."""
        return TradeResultModel(
            success=False,
            result=TradeResult.REJECTED,
            error_code=403,
            error_message="Order placement disabled: MT5 adapter is READ-ONLY (demo-only safety lock)",
        )

    def close_order(self, ticket: str) -> TradeResultModel:
        """Order closing is disabled for demo-only safety."""
        return TradeResultModel(
            success=False,
            result=TradeResult.REJECTED,
            error_code=403,
            error_message="Order closing disabled: MT5 adapter is READ-ONLY (demo-only safety lock)",
        )

    def get_orders(self) -> List[Order]:
        """Read-only retrieval of open/pending orders via ``orders_get()``.

        This never places, modifies, or cancels anything. Returns an empty list
        only when the broker reports no orders or the call is unavailable.
        """
        if not self.is_connected or self._connection._mt5_module is None:
            return []
        try:
            raw_orders = self._connection._mt5_module.orders_get()
            if raw_orders is None:
                return []
            return [self._convert_order(o) for o in raw_orders]
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Failed to get orders: %s", exc)
            return []

    def get_positions(self) -> List[Position]:
        """Read-only retrieval of open positions via ``positions_get()``.

        This never opens, modifies, or closes anything.
        """
        if not self.is_connected or self._connection._mt5_module is None:
            return []
        try:
            raw_positions = self._connection._mt5_module.positions_get()
            if raw_positions is None:
                return []
            return [self._convert_position(p) for p in raw_positions]
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Failed to get positions: %s", exc)
            return []

    # --- MT5 <-> internal model conversion (read-only) ---

    @staticmethod
    def _map_order_type(mt5_type: int) -> OrderType:
        """Map an MT5 order type constant to the internal OrderType."""
        if mt5_type in (0, 1, 8):  # BUY, SELL, CLOSE_BY
            return OrderType.MARKET
        if mt5_type in (2, 3):  # BUY_LIMIT, SELL_LIMIT
            return OrderType.LIMIT
        if mt5_type in (4, 5):  # BUY_STOP, SELL_STOP
            return OrderType.STOP
        if mt5_type in (6, 7):  # BUY_STOP_LIMIT, SELL_STOP_LIMIT
            return OrderType.STOP_LIMIT
        return OrderType.MARKET

    @staticmethod
    def _map_order_status(mt5_state: int) -> OrderStatus:
        """Map an MT5 order state constant to the internal OrderStatus."""
        mapping = {
            0: OrderStatus.OPEN,              # ORDER_STATE_STARTED
            1: OrderStatus.OPEN,              # ORDER_STATE_PLACED
            2: OrderStatus.CANCELLED,         # ORDER_STATE_CANCELED
            3: OrderStatus.PARTIALLY_FILLED,  # ORDER_STATE_PARTIAL
            4: OrderStatus.FILLED,            # ORDER_STATE_FILLED
            5: OrderStatus.REJECTED,          # ORDER_STATE_REJECTED
            6: OrderStatus.EXPIRED,           # ORDER_STATE_EXPIRED
            7: OrderStatus.OPEN,              # ORDER_STATE_REQUEST_ADD
            8: OrderStatus.OPEN,              # ORDER_STATE_REQUEST_MODIFY
            9: OrderStatus.OPEN,              # ORDER_STATE_REQUEST_CANCEL
        }
        return mapping.get(mt5_state, OrderStatus.OPEN)

    def _convert_order(self, o) -> Order:
        """Convert an MT5 order object to the internal Order model."""
        mt5_type = int(getattr(o, "type", 0))
        side = OrderSide.BUY if mt5_type % 2 == 0 else OrderSide.SELL
        volume = getattr(o, "volume_current", None)
        if not volume:
            volume = getattr(o, "volume_initial", 0)
        price_open = float(getattr(o, "price_open", 0) or 0)
        sl = float(getattr(o, "sl", 0) or 0)
        tp = float(getattr(o, "tp", 0) or 0)
        time_setup = int(getattr(o, "time_setup", 0) or 0)
        magic = int(getattr(o, "magic", 0) or 0)
        return Order(
            ticket=str(getattr(o, "ticket", "")),
            symbol=getattr(o, "symbol", ""),
            side=side,
            order_type=self._map_order_type(mt5_type),
            volume=Decimal(str(volume)),
            status=self._map_order_status(int(getattr(o, "state", 1))),
            price=Decimal(str(price_open)) if price_open > 0 else None,
            stop_loss=Decimal(str(sl)) if sl > 0 else None,
            take_profit=Decimal(str(tp)) if tp > 0 else None,
            open_time=datetime.fromtimestamp(time_setup, tz=timezone.utc) if time_setup > 0 else None,
            comment=getattr(o, "comment", "") or None,
            magic_number=magic if magic != 0 else None,
        )

    def _convert_position(self, p) -> Position:
        """Convert an MT5 position object to the internal Position model."""
        pos_type = int(getattr(p, "type", 0))
        side = OrderSide.BUY if pos_type == 0 else OrderSide.SELL
        price_open = float(getattr(p, "price_open", 0) or 0)
        price_current = float(getattr(p, "price_current", 0) or 0)
        sl = float(getattr(p, "sl", 0) or 0)
        tp = float(getattr(p, "tp", 0) or 0)
        profit = float(getattr(p, "profit", 0) or 0)
        time_open = int(getattr(p, "time", 0) or 0)
        magic = int(getattr(p, "magic", 0) or 0)
        return Position(
            ticket=str(getattr(p, "ticket", "")),
            symbol=getattr(p, "symbol", ""),
            side=side,
            volume=Decimal(str(getattr(p, "volume", 0) or 0)),
            open_price=Decimal(str(price_open)),
            current_price=Decimal(str(price_current)),
            stop_loss=Decimal(str(sl)) if sl > 0 else None,
            take_profit=Decimal(str(tp)) if tp > 0 else None,
            profit=Decimal(str(profit)),
            open_time=datetime.fromtimestamp(time_open, tz=timezone.utc) if time_open > 0 else None,
            comment=getattr(p, "comment", "") or None,
            magic_number=magic if magic != 0 else None,
        )

    # --- Additional MT5-specific methods ---

    def get_symbol_mapping(self) -> Dict[str, str]:
        """Get canonical -> broker symbol mapping."""
        return dict(self._symbol_mapping)

    def get_discovery_report(self) -> str:
        """Get symbol discovery report."""
        if self._symbol_discovery:
            return self._symbol_discovery.generate_discovery_report()
        return "No discovery performed yet"

    def get_market_data(self) -> Optional[MT5MarketData]:
        """Get market data retriever for direct access."""
        return self._market_data

    def run_diagnostics(self) -> dict:
        """Run connection diagnostics."""
        if not self._connection.is_initialized:
            return {
                "status": "not_initialized",
                "python_version": "3.13+",
                "mt5_package": "not_loaded",
            }

        terminal_info = self._connection.terminal_info
        account_summary = self._account_info.get_safe_account_summary() if self._account_info else {}

        return {
            "status": "connected" if self.is_connected else "disconnected",
            "python_version": "3.13+",
            "mt5_package_version": getattr(self._connection._mt5_module, '__version__', 'unknown') if self._connection._mt5_module else 'not_loaded',
            "terminal_version": terminal_info.version if terminal_info else 'unknown',
            "terminal_build": terminal_info.build if terminal_info else 0,
            "account_mode": account_summary.get("mode", "unknown"),
            "server": account_summary.get("server", "unknown"),
            "discovered_symbols": len(self._symbol_discovery._all_symbols) if self._symbol_discovery else 0,
            "mapped_symbols": len(self._mappings),
            "symbol_mapping": self._symbol_mapping,
        }