"""Circuit breaker and emergency risk controls.

Manages configurable risk lockouts with trigger timestamps, audit history, and
explicit reset conditions. A lockout is not automatically cleared by restart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from src.risk_management.base import (
    CircuitBreakerReason,
    CircuitBreakerState,
)


@dataclass(frozen=True)
class CircuitBreakerResult:
    locked: bool
    reason: Optional[CircuitBreakerReason]
    state: CircuitBreakerState
    message: str
    can_reset: bool


class CircuitBreaker:
    """Evaluates and maintains circuit-breaker lockout state."""

    def __init__(self, state: Optional[CircuitBreakerState] = None) -> None:
        self._state = state or CircuitBreakerState()

    @property
    def state(self) -> CircuitBreakerState:
        return self._state

    def is_locked(self) -> bool:
        if not self._state.active:
            return False
        # Lockout persists until explicitly reset, even across restarts.
        return True

    def evaluate(
        self,
        reason: Optional[CircuitBreakerReason],
        triggered_at: datetime,
        cooldown_minutes: int = 60,
    ) -> CircuitBreakerResult:
        """Evaluate whether a condition should trip the circuit breaker.

        Returns a new state with the breaker active if tripped.
        """
        if reason is None:
            return CircuitBreakerResult(
                locked=self.is_locked(),
                reason=self._state.reason,
                state=self._state,
                message="No circuit-breaker condition",
                can_reset=not self._state.reset_required,
            )

        new_state = CircuitBreakerState(
            active=True,
            reason=reason,
            triggered_at=triggered_at,
            lockout_until=triggered_at + timedelta(minutes=cooldown_minutes),
            reset_required=True,
            audit_history=[*self._state.audit_history, {
                "reason": reason.value,
                "triggered_at": triggered_at.isoformat(),
            }],
        )
        self._state = new_state
        return CircuitBreakerResult(
            locked=True,
            reason=reason,
            state=new_state,
            message=f"Circuit breaker tripped: {reason.value}",
            can_reset=False,
        )

    def reset(self, authorized: bool, now: Optional[datetime] = None) -> CircuitBreakerResult:
        """Reset the circuit breaker. Requires explicit authorization."""
        if not authorized:
            return CircuitBreakerResult(
                locked=self.is_locked(),
                reason=self._state.reason,
                state=self._state,
                message="Circuit breaker reset not authorized",
                can_reset=False,
            )
        now = now or datetime.now(timezone.utc)
        self._state = CircuitBreakerState(
            active=False,
            reason=None,
            triggered_at=None,
            lockout_until=None,
            reset_required=False,
            audit_history=[*self._state.audit_history, {
                "action": "reset",
                "at": now.isoformat(),
            }],
        )
        return CircuitBreakerResult(
            locked=False,
            reason=None,
            state=self._state,
            message="Circuit breaker reset (authorized)",
            can_reset=True,
        )

    def record_consecutive_loss(self, count: int, max_consecutive: int) -> CircuitBreakerResult:
        if count >= max_consecutive:
            return self.evaluate(
                CircuitBreakerReason.CONSECUTIVE_LOSSES,
                datetime.now(timezone.utc),
            )
        return CircuitBreakerResult(
            locked=self.is_locked(),
            reason=self._state.reason,
            state=self._state,
            message=f"Consecutive losses {count} below threshold {max_consecutive}",
            can_reset=not self._state.reset_required,
        )
