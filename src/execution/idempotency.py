"""Phase 9 execution idempotency.

Durable duplicate detection based on request fingerprints. Ensures restarting
the application cannot generate a duplicate order from an already-processed
signal, and concurrent submissions are prevented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

from src.execution.execution_journal import ExecutionJournal
from src.execution.models import (
    compute_fingerprint,
    ExecutionRecord,
    ExecutionState,
)


@dataclass
class IdempotencyResult:
    duplicate: bool
    existing_execution_id: Optional[str]
    existing_state: Optional[ExecutionState]
    fingerprint: str


class IdempotencyManager:
    """Detects duplicate execution requests via fingerprints."""

    def __init__(self, journal: ExecutionJournal) -> None:
        self.journal = journal
        self._pending: Dict[str, str] = {}  # fingerprint -> execution_id

    def check_duplicate(
        self,
        *,
        signal_id: str,
        symbol: str,
        side: str,
        volume,
        entry_price,
        stop_loss_price,
        take_profit_price,
        magic_number: int,
        mode: str,
    ) -> IdempotencyResult:
        from decimal import Decimal

        fingerprint = compute_fingerprint(
            signal_id=signal_id,
            symbol=symbol,
            side=side,
            volume=Decimal(str(volume)),
            entry_price=Decimal(str(entry_price)),
            stop_loss_price=(
                Decimal(str(stop_loss_price)) if stop_loss_price is not None else None
            ),
            take_profit_price=(
                Decimal(str(take_profit_price)) if take_profit_price is not None else None
            ),
            magic_number=magic_number,
            mode=mode,
        )
        # Check pending in-memory submissions first.
        if fingerprint in self._pending:
            existing_id = self._pending[fingerprint]
            existing = self.journal.get(existing_id)
            return IdempotencyResult(
                duplicate=True,
                existing_execution_id=existing_id,
                existing_state=existing.state if existing else None,
                fingerprint=fingerprint,
            )
        # Check durable journal.
        for record in self.journal.load_all():
            if record.request_fingerprint == fingerprint:
                return IdempotencyResult(
                    duplicate=True,
                    existing_execution_id=record.execution_id,
                    existing_state=record.state,
                    fingerprint=fingerprint,
                )
        return IdempotencyResult(
            duplicate=False,
            existing_execution_id=None,
            existing_state=None,
            fingerprint=fingerprint,
        )

    def register_pending(self, fingerprint: str, execution_id: str) -> None:
        self._pending[fingerprint] = execution_id

    def clear_pending(self, fingerprint: str) -> None:
        self._pending.pop(fingerprint, None)

    def record_submission_intent(self, record: ExecutionRecord) -> None:
        self.journal.append(record)
        if record.request_fingerprint:
            self._pending[record.request_fingerprint] = record.execution_id
