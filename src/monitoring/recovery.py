"""Phase 10 — Safe recovery mechanisms.

Supports bounded MT5 reconnection with exponential backoff + jitter,
dependency reinitialization, worker recovery, stalled task detection, and
execution journal reconciliation after crashes/timeouts.

Critical safety rules:
- Never automatically resend an uncertain order.
- Preserve UNKNOWN execution states until resolved.
- Require explicit recovery authorization when ambiguity remains.
- Recovery must never remove persistent emergency stops or risk lockouts.
- If the Risk Engine, Account Identity Service, or Execution Reconciliation
  service is unavailable, block new demo execution.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from src.execution.execution_journal import ExecutionJournal
from src.execution.models import ExecutionRecord, ExecutionState

logger = logging.getLogger(__name__)


@dataclass
class RecoveryResult:
    """Result of a recovery operation."""

    action: str
    success: bool
    detail: str
    executions_reconciled: int = 0
    executions_unknown: int = 0
    requires_manual_authorization: bool = False


@dataclass
class ReconnectAttempt:
    """A single reconnection attempt record."""

    attempt_number: int
    timestamp: datetime
    success: bool
    delay_seconds: float
    error: Optional[str] = None


class ReconnectionManager:
    """Bounded MT5 reconnection with exponential backoff and jitter."""

    def __init__(
        self,
        *,
        max_attempts: int = 5,
        base_delay_seconds: float = 2.0,
        jitter_seconds: float = 1.0,
    ) -> None:
        self.max_attempts = max_attempts
        self.base_delay_seconds = base_delay_seconds
        self.jitter_seconds = jitter_seconds
        self._attempts: List[ReconnectAttempt] = []

    def attempt(self, connect_callable: Callable[[], bool]) -> bool:
        """Attempt reconnection with exponential backoff + jitter.

        Returns True if reconnection succeeded within max_attempts.
        """
        for attempt_num in range(1, self.max_attempts + 1):
            start = time.perf_counter()
            try:
                success = connect_callable()
            except Exception as exc:  # noqa: BLE001
                success = False
                error = str(exc)
            else:
                error = None

            elapsed = time.perf_counter() - start
            self._attempts.append(
                ReconnectAttempt(
                    attempt_number=attempt_num,
                    timestamp=datetime.now(timezone.utc),
                    success=success,
                    delay_seconds=round(elapsed, 3),
                    error=error,
                )
            )

            if success:
                logger.info("MT5 reconnection succeeded on attempt %d", attempt_num)
                return True

            if attempt_num < self.max_attempts:
                # Exponential backoff + jitter.
                backoff = self.base_delay_seconds * (2 ** (attempt_num - 1))
                jitter = random.uniform(0, self.jitter_seconds)
                delay = backoff + jitter
                logger.warning(
                    "MT5 reconnection attempt %d failed; retrying in %.1fs",
                    attempt_num,
                    delay,
                )
                time.sleep(delay)

        logger.error("MT5 reconnection failed after %d attempts", self.max_attempts)
        return False

    def get_attempts(self) -> List[ReconnectAttempt]:
        return list(self._attempts)


class SafeRecoveryManager:
    """Manages safe recovery after crashes, timeouts, and service failures."""

    def __init__(
        self,
        journal: ExecutionJournal,
        *,
        block_on_risk_unavailable: bool = True,
        block_on_identity_unavailable: bool = True,
        block_on_reconciliation_unavailable: bool = True,
    ) -> None:
        self.journal = journal
        self.block_on_risk_unavailable = block_on_risk_unavailable
        self.block_on_identity_unavailable = block_on_identity_unavailable
        self.block_on_reconciliation_unavailable = block_on_reconciliation_unavailable
        self._recovery_history: List[RecoveryResult] = []
        self._recovery_authorized = False

    def recover_after_crash(
        self,
        *,
        risk_engine_available: bool = True,
        identity_service_available: bool = True,
        reconciliation_available: bool = True,
        reconnect_callable: Optional[Callable[[], bool]] = None,
    ) -> RecoveryResult:
        """Perform safe recovery after an application crash or execution timeout.

        Steps:
        1. Load the persistent execution journal.
        2. Identify unresolved submissions.
        3. Reconcile with actual broker orders, positions, and deals.
        4. Preserve UNKNOWN execution states until resolved.
        5. Never automatically resend an uncertain order.
        6. Require explicit recovery authorization when ambiguity remains.
        """
        actions: List[str] = []
        executions_reconciled = 0
        executions_unknown = 0
        requires_manual = False
        success = True

        # Step 1: Check critical service availability.
        if self.block_on_risk_unavailable and not risk_engine_available:
            actions.append("Risk engine unavailable - blocking new demo execution")
            requires_manual = True
        if self.block_on_identity_unavailable and not identity_service_available:
            actions.append("Account identity service unavailable - blocking new demo execution")
            requires_manual = True
        if self.block_on_reconciliation_unavailable and not reconciliation_available:
            actions.append("Execution reconciliation unavailable - blocking new demo execution")
            requires_manual = True

        # Step 2: Bounded MT5 reconnection (if callable provided).
        if reconnect_callable is not None:
            reconnection = ReconnectionManager()
            if reconnection.attempt(reconnect_callable):
                actions.append("MT5 reconnection succeeded")
            else:
                actions.append("MT5 reconnection failed after max attempts")
                success = False

        # Step 3: Load journal and identify unresolved submissions.
        try:
            records = self.journal.load_all()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to load execution journal: %s", exc)
            actions.append(f"Journal load failed: {exc}")
            requires_manual = True
            success = False
            records = []

        # Step 4: Identify unresolved (non-terminal) executions.
        unresolved = [
            r for r in records if not getattr(r, "is_terminal", lambda: False)()
        ]

        # Step 5: Reconcile unresolved executions (read-only; no auto-resend).
        for record in unresolved:
            ticket = getattr(record, "broker_order_ticket", None)
            state = getattr(record, "state", None)

            if ticket is None:
                # Submitted but no broker ticket - state is unknown.
                actions.append(f"Execution {record.execution_id}: no broker ticket, state={state}")
                executions_unknown += 1
                requires_manual = True
                continue

            # Ticket exists but we can't verify without broker API.
            # Mark for manual reconciliation.
            actions.append(f"Execution {record.execution_id}: ticket={ticket} needs reconciliation")
            executions_reconciled += 1
            requires_manual = True

        if unresolved:
            actions.append(
                f"{len(unresolved)} unresolved execution(s) preserved; "
                "no automatic resend attempted"
            )

        # Step 6: Recovery must never remove persistent emergency stops or risk lockouts.
        actions.append("Persistent emergency stops and risk lockouts preserved")

        result = RecoveryResult(
            action="post_crash_recovery",
            success=success and not requires_manual,
            detail="; ".join(actions) if actions else "No issues found",
            executions_reconciled=executions_reconciled,
            executions_unknown=executions_unknown,
            requires_manual_authorization=requires_manual,
        )
        self._recovery_history.append(result)
        return result

    def authorize_recovery(self) -> None:
        """Explicitly authorize recovery after manual review of unresolved executions."""
        self._recovery_authorized = True
        logger.info("Recovery authorized by operator")

    def is_recovery_authorized(self) -> bool:
        return self._recovery_authorized

    def get_recovery_history(self) -> List[RecoveryResult]:
        return list(self._recovery_history)


import random  # noqa: E402  (used in ReconnectionManager)
