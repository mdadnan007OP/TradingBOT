"""Phase 9 DEMO_MANUAL approval mechanism.

One-time, time-limited authorization challenge bound to the exact order
fingerprint. Invalidated if any critical order parameter changes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Optional

from src.execution.models import compute_fingerprint


@dataclass(frozen=True)
class ApprovalChallenge:
    token: str
    fingerprint: str
    preview: Dict[str, object]
    created_at: datetime
    expires_at: datetime
    used: bool = False
    approved: bool = False

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_valid(self) -> bool:
        return (not self.used) and self.approved and not self.is_expired


@dataclass
class ApprovalDecision:
    approved: bool
    token: Optional[str]
    reason: str
    expired: bool = False


class ApprovalManager:
    """Manages one-time manual approval challenges for DEMO_MANUAL mode."""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self.ttl_seconds = ttl_seconds
        self._challenges: Dict[str, ApprovalChallenge] = {}
        self._by_fingerprint: Dict[str, str] = {}  # fingerprint -> token

    def create_challenge(
        self,
        *,
        signal_id: str,
        symbol: str,
        side: str,
        volume: Decimal,
        entry_price: Decimal,
        stop_loss_price: Optional[Decimal],
        take_profit_price: Optional[Decimal],
        magic_number: int,
        mode: str,
        preview: Dict[str, object],
    ) -> ApprovalChallenge:
        token = f"auth-{uuid.uuid4().hex[:16]}"
        fingerprint = compute_fingerprint(
            signal_id=signal_id,
            symbol=symbol,
            side=side,
            volume=volume,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            magic_number=magic_number,
            mode=mode,
        )
        now = datetime.now(timezone.utc)
        challenge = ApprovalChallenge(
            token=token,
            fingerprint=fingerprint,
            preview=preview,
            created_at=now,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
        )
        self._challenges[token] = challenge
        self._by_fingerprint[fingerprint] = token
        return challenge

    def get_challenge(self, token: str) -> Optional[ApprovalChallenge]:
        return self._challenges.get(token)

    def get_challenge_by_fingerprint(self, fingerprint: str) -> Optional[ApprovalChallenge]:
        token = self._by_fingerprint.get(fingerprint)
        if token is None:
            return None
        return self._challenges.get(token)

    def approve(self, token: str) -> ApprovalDecision:
        challenge = self._challenges.get(token)
        if challenge is None:
            return ApprovalDecision(
                approved=False,
                token=None,
                reason="Unknown approval token",
            )
        if challenge.is_expired:
            return ApprovalDecision(
                approved=False,
                token=token,
                reason="Approval challenge has expired",
                expired=True,
            )
        if challenge.approved:
            return ApprovalDecision(
                approved=True,
                token=token,
                reason="Already approved",
            )
        # Authorize (one-time). Mark used only at submission time.
        obj = challenge
        self._challenges[token] = ApprovalChallenge(
            token=obj.token,
            fingerprint=obj.fingerprint,
            preview=obj.preview,
            created_at=obj.created_at,
            expires_at=obj.expires_at,
            used=False,
            approved=True,
        )
        return ApprovalDecision(
            approved=True,
            token=token,
            reason="Order approved",
        )

    def validate_for_submission(
        self,
        *,
        signal_id: str,
        symbol: str,
        side: str,
        volume: Decimal,
        entry_price: Decimal,
        stop_loss_price: Optional[Decimal],
        take_profit_price: Optional[Decimal],
        magic_number: int,
        mode: str,
        token: Optional[str] = None,
    ) -> ApprovalDecision:
        """Revalidate an approval immediately before order_send().

        The approval must be bound to the exact fingerprint, approved, not
        expired, and not already consumed by a prior submission.
        """
        fingerprint = compute_fingerprint(
            signal_id=signal_id,
            symbol=symbol,
            side=side,
            volume=volume,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            magic_number=magic_number,
            mode=mode,
        )
        # Resolve challenge by token (if provided) else by fingerprint.
        challenge: Optional[ApprovalChallenge] = None
        if token is not None:
            challenge = self._challenges.get(token)
        if challenge is None:
            challenge = self.get_challenge_by_fingerprint(fingerprint)
        if challenge is None:
            return ApprovalDecision(
                approved=False,
                token=token,
                reason="No approval challenge found for this order fingerprint",
            )
        # Token must match the challenge's token if one was provided.
        if token is not None and challenge.token != token:
            return ApprovalDecision(
                approved=False,
                token=token,
                reason="Approval token does not match this order fingerprint",
            )
        if not challenge.approved:
            return ApprovalDecision(
                approved=False,
                token=challenge.token,
                reason="Order has not been approved",
            )
        if challenge.is_expired:
            return ApprovalDecision(
                approved=False,
                token=challenge.token,
                reason="Approval challenge has expired",
                expired=True,
            )
        if challenge.used:
            return ApprovalDecision(
                approved=False,
                token=challenge.token,
                reason="Approval token already used",
            )
        # Mark consumed (one-time) and approve.
        obj = challenge
        self._challenges[obj.token] = ApprovalChallenge(
            token=obj.token,
            fingerprint=obj.fingerprint,
            preview=obj.preview,
            created_at=obj.created_at,
            expires_at=obj.expires_at,
            used=True,
            approved=True,
        )
        return ApprovalDecision(
            approved=True,
            token=obj.token,
            reason="Approval valid for submission",
        )

    def revoke(self, token: str) -> None:
        self._challenges.pop(token, None)
        challenge = self._challenges.get(token)
        if challenge is None:
            # find by token in values
            for tok, chal in list(self._challenges.items()):
                if chal.token == token:
                    self._by_fingerprint.pop(chal.fingerprint, None)
                    self._challenges.pop(tok, None)
                    break

    def clear_expired(self) -> None:
        now = datetime.now(timezone.utc)
        for token, chal in list(self._challenges.items()):
            if chal.is_expired or chal.used:
                self._by_fingerprint.pop(chal.fingerprint, None)
                self._challenges.pop(token, None)

    @property
    def pending_count(self) -> int:
        return sum(1 for c in self._challenges.values() if not c.used and not c.is_expired)
