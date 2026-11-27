"""Phase 9 execution package.

Exports the ExecutionEngine and supporting components. PAPER mode is the
default; DEMO execution requires explicit configuration and authorization.
"""

import importlib.util
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.execution.account_identity import AccountIdentityVerifier
from src.execution.approval import ApprovalManager
from src.execution.config import ExecutionConfig, ExecutionMode
from src.execution.emergency_stop import EmergencyStop
from src.execution.execution_journal import ExecutionJournal
from src.execution.execution_policy import ExecutionPolicy
from src.execution.idempotency import IdempotencyManager
from src.execution.adapters import PaperExecutionAdapter, DemoMT5ExecutionAdapter
from src.broker import BrokerAdapter, TradeResultModel
from src.engines import TradeExecutionEngine
from src.models import Order, OrderRequest, Position, TradeResult
from src.execution.models import (
    ExecutionRequest,
    ExecutionRecord,
    ExecutionResult,
    ExecutionState,
    OrderFillPolicy,
    BrokerRetCode,
    compute_fingerprint,
    new_execution_id,
    new_authorization_token,
)
from src.execution.order_builder import OrderBuilder
from src.execution.order_manager import OrderManager
from src.execution.position_manager import PositionManager
from src.execution.pre_trade_validator import PreTradeResult, PreTradeValidator
from src.execution.process_lock import ProcessLock
from src.execution.reconciliation import Reconciliation, ReconciliationResult
from src.execution.reporting import ExecutionReporter, ExecutionReport
from src.execution.state_machine import ExecutionStateMachine, TransitionResult
from src.execution.service import ExecutionEngine, ExecutionProposal, ExecutionOutcome
from src.execution.trade_monitor import TradeMonitor, MonitorSnapshot

__all__ = [
    "ExecutionEngine",
    "ExecutionProposal",
    "ExecutionOutcome",
    "ExecutionConfig",
    "ExecutionMode",
    "ExecutionPolicy",
    "ExecutionRequest",
    "ExecutionRecord",
    "ExecutionResult",
    "ExecutionState",
    "OrderFillPolicy",
    "BrokerRetCode",
    "compute_fingerprint",
    "new_execution_id",
    "new_authorization_token",
    "OrderBuilder",
    "OrderManager",
    "PositionManager",
    "PreTradeValidator",
    "PreTradeResult",
    "ProcessLock",
    "Reconciliation",
    "ReconciliationResult",
    "ExecutionReporter",
    "ExecutionReport",
    "ExecutionStateMachine",
    "TransitionResult",
    "TradeMonitor",
    "MonitorSnapshot",
    "AccountIdentityVerifier",
    "ApprovalManager",
    "EmergencyStop",
    "ExecutionJournal",
    "IdempotencyManager",
    "PaperExecutionAdapter",
    "DemoMT5ExecutionAdapter",
]


def build_engine(
    config: Optional[ExecutionConfig] = None,
    gateway=None,
    journal=None,
    cli_demo_auto: bool = False,
) -> ExecutionEngine:
    """Factory to build a wired ExecutionEngine with sensible defaults."""
    if config is None:
        config = ExecutionConfig.from_env(cli_demo_auto=cli_demo_auto)
    if journal is None:
        journal = ExecutionJournal()
    idempotency = IdempotencyManager(journal)
    state_machine = ExecutionStateMachine()
    emergency_stop = EmergencyStop()
    approval = ApprovalManager(
        ttl_seconds=config.demo_approval_ttl_seconds
    )
    account_verifier = AccountIdentityVerifier(
        connection=None,  # set by caller when MT5 is available
        config=config,
    )
    order_builder = OrderBuilder(magic_number=config.magic_number)
    process_lock = ProcessLock()
    if gateway is None:
        from src.execution.adapters.paper_adapter import PaperExecutionAdapter

        gateway = PaperExecutionAdapter()

    risk_engine = None
    signal_validator = None
    order_manager = OrderManager(
        gateway=gateway,
        journal=journal,
        idempotency=idempotency,
        state_machine=state_machine,
        approval=approval,
        emergency_stop=emergency_stop,
        account_verifier=account_verifier,
    )
    position_manager = PositionManager(
        magic_number=config.magic_number, journal=journal
    )
    trade_monitor = TradeMonitor(gateway=gateway, journal=journal)
    reconciliation = Reconciliation(gateway=gateway, journal=journal)
    reporter = ExecutionReporter(journal=journal)

    engine = ExecutionEngine(
        config=config,
        gateway=gateway,
        journal=journal,
        idempotency=idempotency,
        state_machine=state_machine,
        emergency_stop=emergency_stop,
        account_verifier=account_verifier,
        approval=approval,
        risk_engine=risk_engine,
        signal_validator=signal_validator,
        order_builder=order_builder,
        order_manager=order_manager,
        position_manager=position_manager,
        trade_monitor=trade_monitor,
        reconciliation=reconciliation,
        reporter=reporter,
        process_lock=process_lock,
        cli_demo_auto=cli_demo_auto,
    )
    return engine


# ---------------------------------------------------------------------------
# Backward compatibility: re-export TradeExecutionEngineImpl from the original
# src/execution.py module (now shadowed by this package). Existing modules and
# tests that import it continue to work unchanged.
# ---------------------------------------------------------------------------
_legacy_path = Path(__file__).resolve().parent.parent / "execution.py"
if _legacy_path.exists():
    _spec = importlib.util.spec_from_file_location("src.execution._legacy", _legacy_path)
    _legacy_mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_legacy_mod)
    TradeExecutionEngineImpl = _legacy_mod.TradeExecutionEngineImpl
    __all__.append("TradeExecutionEngineImpl")


# Backward-compatible Phase 1 execution engine defined directly in the package
# namespace so that existing tests can patch src.execution.CONFIG.
class TradeExecutionEngineImpl(TradeExecutionEngine):
    """Default implementation of the trade execution engine (Phase 1).

    Rejects requests when live trading is locked/disabled and routes approved
    requests through a BrokerAdapter. Kept in the src.execution package
    namespace for backward compatibility.
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
        if CONFIG.trading.live_locked:
            return TradeResultModel(
                success=False,
                result=TradeResult.REJECTED,
                error_code=403,
                error_message="Live trading is locked in Phase 1. Enable only in a later phase.",
            )
        if self._risk_manager is not None:
            try:
                positions: List[Position] = self._broker.get_positions()
            except Exception as exc:  # pragma: no cover - defensive
                self._logger.warning("Could not fetch positions for risk check: %s", exc)
                positions = []
            validation = self._risk_manager.validate(request, positions)
            if not validation.success:
                return validation
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


def __getattr__(name: str):
    """Lazily load CONFIG from src.config to avoid circular imports."""
    if name == "CONFIG":
        from src.config import CONFIG as _cfg

        return _cfg
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
