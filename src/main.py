"""Application entry point.

A simple, runnable starting point that wires the configuration, logging, mock
broker adapter, and trade execution engine together, then prints a status
summary. No real orders are placed and live trading remains disabled.

Run from the project root:

    python -m src.main
"""

from __future__ import annotations

import logging
import sys
from decimal import Decimal
from typing import List

from src.broker import MockBrokerAdapter
from src.config import CONFIG
from src.engines import TradeExecutionEngine
from src.execution import TradeExecutionEngineImpl
from src.logging_config import setup_logging
from src.models import OrderRequest, OrderSide, OrderType

logger = logging.getLogger(__name__)


def build_demo_order_request(symbol: str) -> OrderRequest:
    """Build a sample (never-submitted) OrderRequest to demonstrate the model."""
    return OrderRequest(
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=Decimal("0.01"),
        comment="Phase 1 demo - not executed",
    )


def main(argv: List[str]) -> int:
    # Initialize logging first.
    setup_logging()
    logger.info("Forex Trading Bot starting (Phase 1 foundation)")

    # Report configuration (no secrets logged).
    logger.info("Trading mode: %s | Live locked: %s", CONFIG.trading.mode, CONFIG.trading.live_locked)
    logger.info("Default symbols: %s", ", ".join(CONFIG.trading.default_symbols))

    # Initialize mock broker.
    broker = MockBrokerAdapter()
    connected = broker.connect()
    logger.info("Mock broker connected: %s", connected)

    # Wire the execution engine (risk manager not yet implemented in Phase 1).
    execution_engine: TradeExecutionEngine = TradeExecutionEngineImpl(broker=broker, risk_manager=None)
    logger.info("Trade execution engine ready")

    # Demonstrate a sample order request (NOT submitted).
    demo_request = build_demo_order_request(CONFIG.trading.default_symbols[0])
    logger.info(
        "Demo order request (not submitted): %s %s %s @ %s lots",
        demo_request.side.value.upper(),
        demo_request.symbol,
        demo_request.order_type.value,
        demo_request.volume,
    )

    # Show account snapshot.
    account = broker.get_account_info()
    if account:
        logger.info(
            "Account: %s | balance=%s %s | trade_allowed=%s",
            account.login,
            account.balance,
            account.currency,
            account.trade_allowed,
        )

    # Show instruments.
    instruments = broker.get_instruments()
    logger.info("Available instruments: %d", len(instruments))

    broker.disconnect()
    logger.info("Forex Trading Bot stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
