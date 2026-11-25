"""Phase 9 execution interfaces.

The ExecutionGateway ABC isolates broker communication. Only the dedicated demo
execution adapter may implement order_check/order_send trading calls.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.execution.models import (
    ExecutionRecord,
    ExecutionRequest,
    ExecutionResult,
    ExecutionState,
)
from src.models import AccountInfo, Instrument, Order, OrderRequest, Position, Tick


class ExecutionGateway(ABC):
    """Abstract execution gateway. Paper and demo adapters implement this."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def mode(self) -> str:
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        ...

    @abstractmethod
    def connect(self) -> bool:
        ...

    @abstractmethod
    def disconnect(self) -> bool:
        ...

    # --- account / market --------------------------------------------------
    @abstractmethod
    def get_account_info(self) -> Optional[AccountInfo]:
        ...

    @abstractmethod
    def get_instruments(self) -> List[Instrument]:
        ...

    @abstractmethod
    def get_tick(self, symbol: str) -> Optional[Tick]:
        ...

    @abstractmethod
    def get_symbol_spec(self, symbol: str) -> Optional[Dict[str, Any]]:
        ...

    # --- order lifecycle ----------------------------------------------------
    @abstractmethod
    def order_check(self, request: OrderRequest) -> ExecutionResult:
        """Pre-trade preflight. Never a trade execution."""

    @abstractmethod
    def order_send(self, request: OrderRequest) -> ExecutionResult:
        """Submit an order. Only the demo trading adapter may implement."""

    @abstractmethod
    def get_orders(self) -> List[Order]:
        ...

    @abstractmethod
    def get_positions(self) -> List[Position]:
        ...

    @abstractmethod
    def get_history_orders(self) -> List[Order]:
        ...

    @abstractmethod
    def get_history_deals(self) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def can_submit_orders(self) -> bool:
        """True only when this adapter is authorized to submit orders."""
