"""Phase 9 ExecutionEngine service.

Orchestrates the full execution pipeline:
signal intake -> risk validation -> pre-trade validation -> order construction
-> user authorization -> broker communication -> execution tracking ->
reconciliation -> audit/reporting.

PAPER mode is the default and never submits to a broker. Only the dedicated
demo MT5 adapter may call MT5 trading functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.execution.account_identity import AccountIdentityVerifier
from src.execution.approval import ApprovalManager
from src.execution.config import ExecutionConfig, ExecutionMode
from src.execution.emergency_stop import EmergencyStop
from src.execution.execution_journal import ExecutionJournal
from src.execution.execution_policy import ExecutionPolicy
from src.execution.idempotency import IdempotencyManager
from src.execution.interfaces import ExecutionGateway
from src.execution.models import (
    ExecutionRequest,
    ExecutionRecord,
    ExecutionResult,
    ExecutionState,
    OrderFillPolicy,
    compute_fingerprint,
    new_execution_id,
    new_authorization_token,
)
from src.execution.order_builder import OrderBuilder
from src.execution.order_manager import OrderManager
from src.execution.position_manager import PositionManager
from src.execution.pre_trade_validator import PreTradeResult, PreTradeValidator
from src.execution.process_lock import ProcessLock
from src.execution.reconciliation import Reconciliation
from src.execution.reporting import ExecutionReporter
from src.execution.state_machine import ExecutionStateMachine
from src.execution.trade_monitor import TradeMonitor
from src.models import OrderRequest, OrderSide


@dataclass
class ExecutionProposal:
    """A fully validated, risk-approved execution proposal (not yet submitted)."""

    execution_id: str
    signal_id: str
    preview: Dict[str, Any]
    order_request: OrderRequest
    execution_request: ExecutionRequest
    pre_trade_result: PreTradeResult
    requires_approval: bool
    authorization_token: Optional[str] = None


@dataclass
class ExecutionOutcome:
    proposal: ExecutionProposal
    result: ExecutionResult
    submitted: bool
    reason: str


class ExecutionEngine:
    """Main execution orchestrator."""

    def __init__(
        self,
        config: ExecutionConfig,
        gateway: ExecutionGateway,
        journal: ExecutionJournal,
        idempotency: IdempotencyManager,
        state_machine: ExecutionStateMachine,
        emergency_stop: EmergencyStop,
        account_verifier: AccountIdentityVerifier,
        approval: ApprovalManager,
        risk_engine: Any,
        signal_validator: Any,
        order_builder: OrderBuilder,
        order_manager: OrderManager,
        position_manager: PositionManager,
        trade_monitor: TradeMonitor,
        reconciliation: Reconciliation,
        reporter: ExecutionReporter,
        process_lock: ProcessLock,
        cli_demo_auto: bool = False,
    ) -> None:
        self.config = config
        self.gateway = gateway
        self.journal = journal
        self.idempotency = idempotency
        self.state_machine = state_machine
        self.emergency_stop = emergency_stop
        self.account_verifier = account_verifier
        self.approval = approval
        self.risk_engine = risk_engine
        self.signal_validator = signal_validator
        self.order_builder = order_builder
        self.order_manager = order_manager
        self.position_manager = position_manager
        self.trade_monitor = trade_monitor
        self.reconciliation = reconciliation
        self.reporter = reporter
        self.process_lock = process_lock
        self.cli_demo_auto = cli_demo_auto
        self.policy = ExecutionPolicy(config, cli_demo_auto=cli_demo_auto)
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Start the execution engine. Acquires process lock."""
        if self._running:
            return True
        # Acquire process lock to prevent concurrent instances.
        lock_result = self.process_lock.acquire()
        if not lock_result.acquired:
            return False
        self._running = True
        return True

    def stop(self) -> bool:
        """Safe shutdown: stop new entries, complete reconciliation, no liquidation."""
        self._running = False
        self.process_lock.release()
        return True

    def is_running(self) -> bool:
        return self._running

    def policy_decision(self) -> Any:
        return self.policy.decide()

    # ------------------------------------------------------------------
    # Signal intake -> proposal (Stage A + B preview)
    # ------------------------------------------------------------------

    def propose_execution(
        self,
        *,
        signal_id: str,
        strategy_name: str,
        strategy_version: str,
        symbol: str,
        side: str,
        volume: Decimal,
        entry_reference_price: Decimal,
        stop_loss_price: Optional[Decimal],
        take_profit_price: Optional[Decimal],
        risk_decision: Any,
        risk_policy_version: str,
    ) -> ExecutionProposal:
        """Build a validated execution proposal (does not submit)."""

        # Policy gate.
        decision = self.policy.decide()
        if not decision.permitted:
            raise PermissionError(f"Execution not permitted: {decision.reason}")

        # Pre-trade validation (Stage A).
        pre_trade = PreTradeValidator(
            config=self.config,
            account_verifier=self.account_verifier,
            emergency_stop=self.emergency_stop,
            risk_engine=self.risk_engine,
            signal_validator=self.signal_validator,
            market_data=self.gateway,
            broker_gateway=self.gateway,
        ).validate(
            signal_id=signal_id,
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            symbol=symbol,
            side=side,
            volume=volume,
            entry_reference_price=entry_reference_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            risk_decision=risk_decision,
            risk_policy_version=risk_policy_version,
        )
        if not pre_trade.passed:
            raise ValueError(f"Pre-trade validation failed: {', '.join(pre_trade.rejection_reasons)}")

        # Build normalized order request.
        spec = self.gateway.get_symbol_spec(symbol) or {}
        tick = self.gateway.get_tick(symbol)
        bid = tick.bid if tick else Decimal("0")
        ask = tick.ask if tick else Decimal("0")
        build = self.order_builder.build_market_order(
            symbol=symbol,
            side=side,
            volume=volume,
            entry_reference_price=entry_reference_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            tick_bid=bid,
            tick_ask=ask,
            price_precision=int(spec.get("digits", 5)),
            tick_size=spec.get("tick_size", Decimal("0.00001")),
            lot_step=spec.get("lot_step", Decimal("0.01")),
            min_lot=spec.get("min_lot", Decimal("0.01")),
            max_lot=spec.get("max_lot", Decimal("100.0")),
            stop_level=spec.get("stop_level", Decimal("0")),
            deviation_points=self.config.max_deviation_points,
        )
        order_request = build.request

        # Execution request for journaling.
        exec_request = pre_trade.execution_request or ExecutionRequest(
            execution_id=new_execution_id(),
            signal_id=signal_id,
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            symbol=symbol,
            side=side,
            volume=order_request.volume,
            entry_reference_price=entry_reference_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            risk_decision_id=getattr(risk_decision, "signal_id", ""),
            monetary_risk=getattr(risk_decision, "monetary_risk", Decimal("0")),
            risk_percent=getattr(risk_decision, "risk_percent", Decimal("0")),
            fill_policy=OrderFillPolicy.RETURN,
            deviation_points=self.config.max_deviation_points,
            magic_number=self.config.magic_number,
            comment=order_request.comment or "",
            execution_mode=self.config.mode.value,
            created_at=datetime.now(timezone.utc),
        )

        requires_approval = (
            decision.requires_manual_approval and self.config.demo_trading_permitted
        )
        auth_token = None
        if requires_approval:
            chal = self.approval.create_challenge(
                signal_id=signal_id,
                symbol=symbol,
                side=side,
                volume=order_request.volume,
                entry_price=order_request.price or Decimal("0"),
                stop_loss_price=order_request.stop_loss,
                take_profit_price=order_request.take_profit,
                magic_number=self.config.magic_number,
                mode=self.config.mode.value,
                preview=pre_trade.preview,
            )
            auth_token = chal.token

        return ExecutionProposal(
            execution_id=exec_request.execution_id,
            signal_id=signal_id,
            preview=pre_trade.preview,
            order_request=order_request,
            execution_request=exec_request,
            pre_trade_result=pre_trade,
            requires_approval=requires_approval,
            authorization_token=auth_token,
        )

    # ------------------------------------------------------------------
    # Stage B: authorization + submission
    # ------------------------------------------------------------------

    def authorize_and_submit(
        self,
        proposal: ExecutionProposal,
        *,
        approval_token: Optional[str] = None,
    ) -> ExecutionOutcome:
        """Authorize (if required) and submit the proposal. PAPER simulates."""

        # Emergency block check.
        if self.emergency_stop.is_execution_blocked():
            result = ExecutionResult(
                execution_id=proposal.execution_id,
                success=False,
                state=ExecutionState.REJECTED,
                error_message="Blocked by emergency circuit breakers",
                retry_permitted=False,
            )
            return ExecutionOutcome(proposal=proposal, result=result, submitted=False, reason="emergency_blocked")

        # Idempotency: block duplicate execution of the same order fingerprint
        # before registering the current intent (so we never match ourselves).
        fp = compute_fingerprint(
            signal_id=proposal.signal_id,
            symbol=proposal.order_request.symbol,
            side=proposal.order_request.side.value,
            volume=proposal.order_request.volume,
            entry_price=proposal.order_request.price or Decimal("0"),
            stop_loss_price=proposal.order_request.stop_loss,
            take_profit_price=proposal.order_request.take_profit,
            magic_number=self.config.magic_number,
            mode=self.config.mode.value,
        )
        dup = self.idempotency.check_duplicate(
            signal_id=proposal.signal_id,
            symbol=proposal.order_request.symbol,
            side=proposal.order_request.side.value,
            volume=proposal.order_request.volume,
            entry_price=proposal.order_request.price or Decimal("0"),
            stop_loss_price=proposal.order_request.stop_loss,
            take_profit_price=proposal.order_request.take_profit,
            magic_number=self.config.magic_number,
            mode=self.config.mode.value,
        )
        if dup.duplicate and dup.existing_state not in (
            ExecutionState.REJECTED,
            ExecutionState.CANCELLED,
            ExecutionState.EXPIRED,
        ):
            result = ExecutionResult(
                execution_id=proposal.execution_id,
                success=False,
                state=ExecutionState.REJECTED,
                error_message="Duplicate execution detected",
                retry_permitted=False,
            )
            return ExecutionOutcome(
                proposal=proposal, result=result, submitted=False, reason="duplicate_execution"
            )

        # Persist submission-intent before any broker call / approval gating.
        record = self.order_manager.register_submission_intent(
            execution_id=proposal.execution_id,
            signal_id=proposal.signal_id,
            strategy_name=proposal.execution_request.strategy_name,
            strategy_version=proposal.execution_request.strategy_version,
            symbol=proposal.order_request.symbol,
            side=proposal.order_request.side.value,
            volume=proposal.order_request.volume,
            entry_price=proposal.order_request.price or Decimal("0"),
            stop_loss=proposal.order_request.stop_loss,
            take_profit=proposal.order_request.take_profit,
            risk_decision_id=proposal.execution_request.risk_decision_id,
            monetary_risk=proposal.execution_request.monetary_risk,
            risk_percent=proposal.execution_request.risk_percent,
            fill_policy=proposal.execution_request.fill_policy,
            deviation_points=proposal.execution_request.deviation_points,
            magic_number=self.config.magic_number,
            comment=proposal.order_request.comment or "",
            execution_mode=self.config.mode.value,
            order_request=proposal.order_request,
            pre_trade_result=proposal.pre_trade_result,
            account_identity=proposal.pre_trade_result.account_identity,
            authorization_token=approval_token,
        )

        # Manual approval gate (DEMO_MANUAL).
        if proposal.requires_approval:
            if approval_token is None:
                # Awaiting user approval: transition and wait (do not submit).
                from dataclasses import replace

                self.state_machine.transition(
                    record, ExecutionState.AWAITING_MANUAL_APPROVAL, "Awaiting manual approval"
                )
                updated = replace(record, state=ExecutionState.AWAITING_MANUAL_APPROVAL)
                self.journal.append(updated)
                return ExecutionOutcome(
                    proposal=proposal,
                    result=self.order_manager._result_from_record(updated),
                    submitted=False,
                    reason="awaiting_manual_approval",
                )
            decision = self.approval.validate_for_submission(
                signal_id=proposal.signal_id,
                symbol=proposal.order_request.symbol,
                side=proposal.order_request.side.value,
                volume=proposal.order_request.volume,
                entry_price=proposal.order_request.price or Decimal("0"),
                stop_loss_price=proposal.order_request.stop_loss,
                take_profit_price=proposal.order_request.take_profit,
                magic_number=self.config.magic_number,
                mode=self.config.mode.value,
                token=approval_token,
            )
            if not decision.approved:
                self.order_manager._fail_record(record, decision.reason)
                return ExecutionOutcome(
                    proposal=proposal,
                    result=self.order_manager._result_from_record(record),
                    submitted=False,
                    reason=decision.reason,
                )

        # Submit via gateway (demo adapter only; paper returns simulated).
        result = self.gateway.order_send(proposal.order_request)

        # Record broker response.
        record = self._apply_result(record, result)
        return ExecutionOutcome(
            proposal=proposal, result=result, submitted=True, reason="submitted"
        )

    def _apply_result(self, record: ExecutionRecord, result: ExecutionResult) -> ExecutionRecord:
        from dataclasses import replace

        self.state_machine.transition(record, result.state, result.error_message or "")
        updated = replace(
            record,
            state=result.state,
            submitted_at=datetime.now(timezone.utc),
            broker_order_ticket=result.ticket,
            filled_volume=result.filled_volume,
            filled_price=result.filled_price,
            remaining_volume=result.remaining_volume,
            broker_retcode=result.broker_retcode,
            broker_comment=result.broker_comment,
            execution_timestamp=datetime.now(timezone.utc),
            reason=result.error_message,
            reconciliation_status="unreconciled",
        )
        self.journal.append(updated)
        return updated

    # ------------------------------------------------------------------
    # Monitoring / reconciliation / reporting
    # ------------------------------------------------------------------

    def snapshot(self, account_identity: Optional[Any] = None):
        return self.trade_monitor.snapshot(account_identity)

    def reconcile(self, account_identity: Optional[Any] = None):
        return self.reconciliation.reconcile_all(account_identity)

    def report(self, snapshot, account_identity: Optional[Any] = None):
        return self.reporter.report(snapshot, account_identity)

    def bot_positions(self, positions):
        return self.position_manager.bot_positions(positions)

    def can_modify_position(self, position, account_identity: Optional[Any] = None) -> bool:
        return self.position_manager.can_modify(position, account_identity)
