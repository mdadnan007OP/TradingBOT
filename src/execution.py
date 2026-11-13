"""Trade Execution Engine (Phase 1 skeleton).

Validates order requests through the centralized risk manager and routes them
to the broker adapter. In Phase 1 this wires the mock broker and risk interface
together without placing any real orders. Live routing remains locked.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from src.broker import BrokerAdapter, TradeResultModel
from src.config import CONFIG
from src.engines import TradeExecutionEngine
from src.models import Order, OrderRequest, Position, TradeResult

logger = logging.getLogger(__name__)


class TradeExecutionEngineImpl(TradeExecutionEngine):
    """Default implementation of the trade execution engine.

    Responsibilities:
        * Reject requests when live trading is locked/disabled.
        * Delegate risk validation to a ``RiskManager`` (when provided).
        * Route approved requests through a ``BrokerAdapter``.
    """

    def __init__(
        self,
        broker: BrokerAdapter,
        risk_manager: Optional[object] = None,
    ) -> None:
        self._broker = broker
        self._risk_manager = risk_manager
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def execute(self, request: OrderRequest) -> TradeResultModel:
        # Safety gate: live trading must be explicitly unlocked before any order
        # is routed to a broker capable of live execution.
        if CONFIG.trading.live_locked:
            return TradeResultModel(
                success=False,
                result=TradeResult.REJECTED,
                error_code=403,
                error_message="Live trading is locked in Phase 1. Enable only in a later phase.",
            )

        # Risk validation (optional in Phase 1; risk manager is an interface).
        if self._risk_manager is not None:
            try:
                positions: List[Position] = self._broker.get_positions()
            except Exception as exc:  # pragma: no cover - defensive
                self._logger.warning("Could not fetch positions for risk check: %s", exc)
                positions = []
            validation = self._risk_manager.validate(request, positions)
            if not validation.success:
                return validation

        # Route to broker.
        try:
            result = self._broker.place_order(request)
        except Exception as exc:  # fail-safe on unexpected broker errors
            self._logger.exception("Broker raised while placing order: %s", exc)
            return TradeResultModel(
                success=False,
                result=TradeResult.FAILURE,
                error_code=-1,
                error_message=f"Unexpected broker error: {exc}",
            )

        if result.success:
            self._logger.info("Order executed: ticket=%s symbol=%s", result.ticket, request.symbol)
        else:
            self._logger.warning(
                "Order rejected: symbol=%s code=%s msg=%s",
                request.symbol,
                result.error_code,
                result.error_message,
            )
        return result

    def close_position(self, ticket: str) -> TradeResultModel:
        if CONFIG.trading.live_locked:
            return TradeResultModel(
                success=False,
                result=TradeResult.REJECTED,
                error_code=403,
                error_message="Live trading is locked in Phase 1.",
            )
        try:
            return self._broker.close_order(ticket)
        except Exception as exc:  # pragma: no cover - defensive
            self._logger.exception("Broker raised while closing order: %s", exc)
            return TradeResultModel(
                success=False,
                result=TradeResult.FAILURE,
                error_code=-1,
                error_message=f"Unexpected broker error: {exc}",
            )




