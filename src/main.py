"""Application entry point.

Wires the configuration, logging, mock broker, and trade execution engine
together through the Phase 10 ApplicationLifecycleManager, then prints a status
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
from src.monitoring.lifecycle import ApplicationLifecycleManager, LifecycleState
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

    # Create and start the application lifecycle manager.
    lifecycle = ApplicationLifecycleManager()
    lifecycle.update_component_health("logging", True, "Logging initialized")

    started = lifecycle.start()
    if not started:
        logger.error("Application failed to start; state=%s", lifecycle.state.value)
        return 1

    logger.info("Forex Trading Bot started (state=%s)", lifecycle.state.value)

    # Report configuration (no secrets logged).
    logger.info("Trading mode: %s | Live locked: %s", CONFIG.trading.mode, CONFIG.trading.live_locked)
    logger.info("Default symbols: %s", ", ".join(CONFIG.trading.default_symbols))

    # Initialize mock broker.
    broker = MockBrokerAdapter()
    connected = broker.connect()
    logger.info("Mock broker connected: %s", connected)
    lifecycle.update_component_health("broker", connected, "Mock broker connected")

    # Wire the execution engine (risk manager not yet implemented in Phase 1).
    execution_engine: TradeExecutionEngine = TradeExecutionEngineImpl(broker=broker, risk_manager=None)
    logger.info("Trade execution engine ready")
    lifecycle.update_component_health("execution_engine", True, "Execution engine ready")

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

    # Health summary.
    health = lifecycle.get_health_summary()
    logger.info("Health summary: %s", health)

    broker.disconnect()
    lifecycle.stop()
    logger.info("Forex Trading Bot stopped (state=%s)", lifecycle.state.value)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
