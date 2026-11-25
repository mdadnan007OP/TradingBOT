"""Phase 9 order manager.

Submits, tracks and records executions. Persists submission-intent before
calling order_send(). Coordinates idempotency, journaling and state machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.execution.account_identity import AccountIdentity
from src.execution.account_identity import AccountIdentityVerifier
from src.execution.approval import ApprovalManager
from src.execution.emergency_stop import EmergencyStop
from src.execution.execution_journal import ExecutionJournal
from src.execution.idempotency import IdempotencyManager
from src.execution.interfaces import ExecutionGateway
from src.execution.models import (
    ExecutionRequest,
    ExecutionRecord,
    ExecutionResult,
    ExecutionState,
    compute_fingerprint,
    new_execution_id,
)
from src.execution.pre_trade_validator import PreTradeResult
from src.execution.state_machine import ExecutionStateMachine, TransitionResult
from src.models import OrderRequest


@dataclass
class SubmitIntent:
    execution_id: str
    record: ExecutionRecord
    order_request: OrderRequest
    account_identity: Optional[AccountIdentity]
    pre_trade_result: PreTradeResult
    authorization_token: Optional[str] = None


class OrderManager:
    """Manages the full order lifecycle from intent to reconciliation."""

    def __init__(
        self,
        gateway: ExecutionGateway,
        journal: ExecutionJournal,
        idempotency: IdempotencyManager,
        state_machine: ExecutionStateMachine,
        approval: ApprovalManager,
        emergency_stop: EmergencyStop,
        account_verifier: AccountIdentityVerifier,
    ) -> None:
        self.gateway = gateway
        self.journal = journal
        self.idempotency = idempotency
        self.state_machine = state_machine
        self.approval = approval
        self.emergency_stop = emergency_stop
        self.account_verifier = account_verifier

    def register_submission_intent(
        self,
        *,
        execution_id: str,
        signal_id: str,
        strategy_name: str,
        strategy_version: str,
        symbol: str,
        side: str,
        volume: Decimal,
        entry_price: Decimal,
        stop_loss: Optional[Decimal],
        take_profit: Optional[Decimal],
        risk_decision_id: str,
        monetary_risk: Decimal,
        risk_percent: Decimal,
        fill_policy,
        deviation_points: int,
        magic_number: int,
        comment: str,
        execution_mode: str,
        order_request: OrderRequest,
        pre_trade_result: PreTradeResult,
        account_identity: Optional[AccountIdentity],
        authorization_token: Optional[str] = None,
    ) -> ExecutionRecord:
        fingerprint = compute_fingerprint(
            signal_id=signal_id,
            symbol=symbol,
            side=side,
            volume=volume,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            magic_number=magic_number,
            mode=execution_mode,
        )
        record = ExecutionRecord(
            execution_id=execution_id,
            signal_id=signal_id,
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            symbol=symbol,
            side=side,
            volume=volume,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            state=ExecutionState.PRE_TRADE_CHECKED,
            mode=execution_mode,
            magic_number=magic_number,
            comment=comment,
            created_at=datetime.now(timezone.utc),
            request_fingerprint=fingerprint,
            authorization_token=authorization_token,
            reconciliation_status="unreconciled",
        )
        # Persist submission-intent BEFORE any broker call.
        self.journal.append(record)
        self.idempotency.register_pending(fingerprint, execution_id)
        return record

    def submit(
        self,
        record: ExecutionRecord,
        order_request: OrderRequest,
        *,
        require_approval: bool = True,
        authorization_token: Optional[str] = None,
    ) -> ExecutionResult:
        """Submit an order through the gateway with state transitions."""
        # Emergency block.
        if self.emergency_stop.is_execution_blocked():
            self._fail_record(record, "Blocked by emergency circuit breakers")
            return self._result_from_record(record)

        # Idempotency: duplicate check already done at intent time; re-check.
        fp = record.request_fingerprint or ""
        if fp:
            dup = self.idempotency.check_duplicate(
                signal_id=record.signal_id,
                symbol=record.symbol,
                side=record.side,
                volume=record.volume,
                entry_price=record.entry_price or Decimal("0"),
                stop_loss_price=record.stop_loss_price,
                take_profit_price=record.take_profit_price,
                magic_number=record.magic_number,
                mode=record.mode,
            )
            if dup.duplicate and dup.existing_state not in (
                ExecutionState.REJECTED,
                ExecutionState.CANCELLED,
                ExecutionState.EXPIRED,
            ):
                return ExecutionResult(
                    execution_id=dup.existing_execution_id or record.execution_id,
                    success=False,
                    state=dup.existing_state or ExecutionState.REJECTED,
                    error_message="Duplicate execution detected",
                    retry_permitted=False,
                )

        # Manual approval gate.
        if require_approval and self.gateway.mode == "DEMO":
            if authorization_token is None:
                self._transition(record, ExecutionState.AWAITING_MANUAL_APPROVAL, "Awaiting manual approval")
                return self._result_from_record(record)
            decision = self.approval.validate_for_submission(
                signal_id=record.signal_id,
                symbol=record.symbol,
                side=record.side,
                volume=record.volume,
                entry_price=record.entry_price or Decimal("0"),
                stop_loss_price=record.stop_loss_price,
                take_profit_price=record.take_profit_price,
                magic_number=record.magic_number,
                mode=record.mode,
            )
            if not decision.approved:
                self._fail_record(record, decision.reason)
                return self._result_from_record(record)

        # Transition to SUBMITTED.
        self._transition(record, ExecutionState.SUBMITTED, "Submitting to gateway")

        # Submit via gateway (demo adapter only; paper returns simulated).
        result = self.gateway.order_send(order_request)

        # Record broker response.
        record = self._apply_result(record, result)
        self.journal.append(record)
        self.idempotency.clear_pending(fp)
        return result

    def _apply_result(
        self, record: ExecutionRecord, result: ExecutionResult
    ) -> ExecutionRecord:
        from dataclasses import replace

        state = result.state
        self._transition(record, state, result.error_message or result.broker_comment or "")
        updated = replace(
            record,
            state=state,
            submitted_at=datetime.now(timezone.utc),
            broker_order_ticket=result.ticket,
            broker_deal_ticket=None,
            broker_request_id=None,
            filled_volume=result.filled_volume,
            filled_price=result.filled_price,
            remaining_volume=result.remaining_volume,
            broker_retcode=result.broker_retcode,
            broker_external_code=None,
            broker_comment=result.broker_comment,
            execution_timestamp=datetime.now(timezone.utc),
            reason=result.error_message,
            reconciliation_status="unreconciled",
        )
        return updated

    def _fail_record(self, record: ExecutionRecord, reason: str) -> ExecutionRecord:
        from dataclasses import replace
        self._transition(record, ExecutionState.REJECTED, reason)
        return replace(record, state=ExecutionState.REJECTED, reason=reason)

    def _transition(
        self, record: ExecutionRecord, to_state: ExecutionState, reason: Optional[str]
    ) -> TransitionResult:
        return self.state_machine.transition(record, to_state, reason)

    def _result_from_record(self, record: ExecutionRecord) -> ExecutionResult:
        return ExecutionResult(
            execution_id=record.execution_id,
            success=record.state == ExecutionState.FILLED,
            state=record.state,
            ticket=record.broker_order_ticket,
            symbol=record.symbol,
            volume=record.volume,
            price=record.entry_price,
            filled_volume=record.filled_volume,
            filled_price=record.filled_price,
            broker_retcode=record.broker_retcode,
            broker_comment=record.broker_comment,
            error_code=None if record.state == ExecutionState.FILLED else -1,
            error_message=record.reason,
            reconciled=(record.reconciliation_status == "reconciled"),
            retry_permitted=False,
        )

    def record_submitted_intent(self, record: ExecutionRecord) -> None:
        self.journal.append(record)

    def get_record(self, execution_id: str) -> Optional[ExecutionRecord]:
        return self.journal.get(execution_id)
