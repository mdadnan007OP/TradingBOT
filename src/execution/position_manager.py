"""Phase 9 position manager.

Read-only monitoring of bot-managed positions. Identifies bot-owned positions
via magic number and execution journal. Never manages positions it does not own.
Controlled demo-only methods for SL/TP updates and closing (authorized only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.execution.account_identity import AccountIdentity
from src.execution.execution_journal import ExecutionJournal
from src.execution.models import ExecutionRecord, ExecutionState
from src.models import OrderSide, Position


@dataclass(frozen=True)
class PositionOwnership:
    is_bot_owned: bool
    position: Position
    linked_execution_id: Optional[str]
    magic_number: int


class PositionManager:
    """Tracks bot-managed positions and verifies ownership."""

    def __init__(self, magic_number: int, journal: ExecutionJournal) -> None:
        self.magic_number = magic_number
        self.journal = journal

    def classify_position(self, position: Position) -> PositionOwnership:
        """Determine whether a position belongs to this bot."""
        is_bot = position.magic_number == self.magic_number
        linked_id = None
        if is_bot:
            # Find linked execution record.
            for record in self.journal.load_all():
                if record.state in (ExecutionState.FILLED, ExecutionState.PARTIALLY_FILLED):
                    if record.broker_order_ticket == position.ticket:
                        linked_id = record.execution_id
                        break
        return PositionOwnership(
            is_bot_owned=is_bot,
            position=position,
            linked_execution_id=linked_id,
            magic_number=position.magic_number or 0,
        )

    def bot_positions(self, positions: List[Position]) -> List[PositionOwnership]:
        return [self.classify_position(p) for p in positions if self.classify_position(p).is_bot_owned]

    def non_bot_positions(self, positions: List[Position]) -> List[Position]:
        return [p for p in positions if not self.classify_position(p).is_bot_owned]

    def can_modify(self, position: Position, account_identity: Optional[AccountIdentity]) -> bool:
        """Whether this bot may modify/close the position."""
        if not self.classify_position(position).is_bot_owned:
            return False
        if account_identity is None or not account_identity.verification_passed:
            return False
        if not account_identity.is_demo:
            return False
        return True
