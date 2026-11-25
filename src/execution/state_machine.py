"""Phase 9 execution state machine.

Explicit lifecycle transitions. A request is never FILLED merely because
order_send() returned a non-null response; the broker result must be inspected
and reconciled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.execution.models import ExecutionRecord, ExecutionState


# Valid transitions: from -> set of allowed to states.
_TRANSITIONS: Dict[ExecutionState, List[ExecutionState]] = {
    ExecutionState.CREATED: [
        ExecutionState.PENDING_VALIDATION,
        ExecutionState.REJECTED,
        ExecutionState.CANCELLED,
    ],
    ExecutionState.PENDING_VALIDATION: [
        ExecutionState.RISK_APPROVED,
        ExecutionState.REJECTED,
        ExecutionState.CANCELLED,
    ],
    ExecutionState.RISK_APPROVED: [
        ExecutionState.AWAITING_MANUAL_APPROVAL,
        ExecutionState.PRE_TRADE_CHECKED,
        ExecutionState.REJECTED,
        ExecutionState.CANCELLED,
    ],
    ExecutionState.AWAITING_MANUAL_APPROVAL: [
        ExecutionState.PRE_TRADE_CHECKED,
        ExecutionState.REJECTED,
        ExecutionState.CANCELLED,
        ExecutionState.EXPIRED,
    ],
    ExecutionState.PRE_TRADE_CHECKED: [
        ExecutionState.SUBMITTED,
        ExecutionState.REJECTED,
        ExecutionState.CANCELLED,
    ],
    ExecutionState.SUBMITTED: [
        ExecutionState.ACCEPTED,
        ExecutionState.PARTIALLY_FILLED,
        ExecutionState.FILLED,
        ExecutionState.REJECTED,
        ExecutionState.UNKNOWN,
        ExecutionState.CANCELLED,
    ],
    ExecutionState.ACCEPTED: [
        ExecutionState.PARTIALLY_FILLED,
        ExecutionState.FILLED,
        ExecutionState.REJECTED,
        ExecutionState.CANCELLED,
    ],
    ExecutionState.PARTIALLY_FILLED: [
        ExecutionState.FILLED,
        ExecutionState.REJECTED,
        ExecutionState.CANCELLED,
    ],
    ExecutionState.REJECTED: [],
    ExecutionState.CANCELLED: [],
    ExecutionState.EXPIRED: [],
    ExecutionState.UNKNOWN: [ExecutionState.RECONCILED, ExecutionState.REJECTED],
    ExecutionState.FILLED: [ExecutionState.RECONCILED],
    ExecutionState.RECONCILED: [],
}


@dataclass
class TransitionResult:
    ok: bool
    from_state: ExecutionState
    to_state: ExecutionState
    reason: Optional[str] = None


class ExecutionStateMachine:
    """Enforces valid execution lifecycle transitions."""

    def __init__(self) -> None:
        self._history: List[tuple[ExecutionState, ExecutionState, Optional[str]]] = []

    def can_transition(self, from_state: ExecutionState, to_state: ExecutionState) -> bool:
        if to_state not in _TRANSITIONS.get(from_state, []):
            return False
        return True

    def transition(
        self,
        record: ExecutionRecord,
        to_state: ExecutionState,
        reason: Optional[str] = None,
    ) -> TransitionResult:
        if not self.can_transition(record.state, to_state):
            return TransitionResult(
                ok=False,
                from_state=record.state,
                to_state=to_state,
                reason=(
                    f"Invalid transition {record.state.value} -> {to_state.value}"
                    + (f": {reason}" if reason else "")
                ),
            )
        self._history.append((record.state, to_state, reason))
        return TransitionResult(
            ok=True,
            from_state=record.state,
            to_state=to_state,
            reason=reason,
        )

    @property
    def history(self) -> List[tuple[ExecutionState, ExecutionState, Optional[str]]]:
        return list(self._history)
