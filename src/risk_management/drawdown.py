"""Drawdown tracking and persistence.

Tracks equity and balance high-watermarks, computes current and historical
maximum drawdown, and persists state so a restart cannot reset protection
limits.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Optional

from src.risk_management.models import DrawdownState


@dataclass(frozen=True)
class DrawdownResult:
    equity_drawdown_percent: Decimal
    balance_drawdown_percent: Decimal
    equity_high_watermark: Decimal
    balance_high_watermark: Decimal
    max_equity_drawdown_ever: Decimal
    max_balance_drawdown_ever: Decimal
    within_equity_limit: bool
    within_balance_limit: bool
    limit_breach_reasons: list
    state: DrawdownState


class DrawdownTracker:
    """Tracks drawdown against persisted high-watermarks."""

    def __init__(
        self,
        max_equity_drawdown_percent: Decimal,
        max_balance_drawdown_percent: Decimal,
        state: Optional[DrawdownState] = None,
    ) -> None:
        self.max_equity_drawdown_percent = max_equity_drawdown_percent
        self.max_balance_drawdown_percent = max_balance_drawdown_percent
        self._state = state or DrawdownState(
            equity_high_watermark=Decimal("0"),
            balance_high_watermark=Decimal("0"),
        )

    @property
    def state(self) -> DrawdownState:
        return self._state

    def update(
        self,
        equity: Decimal,
        balance: Decimal,
        now: Optional[datetime] = None,
    ) -> DrawdownResult:
        """Update high-watermarks and compute drawdown.

        High-watermarks only increase (a new peak). A restart loads the
        persisted state so limits are not accidentally reset.
        """
        now = now or datetime.now(timezone.utc)
        reasons: list = []

        eq_hwm = max(self._state.equity_high_watermark, equity)
        bal_hwm = max(self._state.balance_high_watermark, balance)

        eq_dd = self._drawdown(eq_hwm, equity)
        bal_dd = self._drawdown(bal_hwm, balance)

        max_eq_dd = max(self._state.max_equity_drawdown_ever, eq_dd)
        max_bal_dd = max(self._state.max_balance_drawdown_ever, bal_dd)

        within_eq = eq_dd <= self.max_equity_drawdown_percent * Decimal("100")
        within_bal = bal_dd <= self.max_balance_drawdown_percent * Decimal("100")

        if not within_eq:
            reasons.append(
                f"Equity drawdown {eq_dd:.4f}% exceeds limit "
                f"{self.max_equity_drawdown_percent}%"
            )
        if not within_bal:
            reasons.append(
                f"Balance drawdown {bal_dd:.4f}% exceeds limit "
                f"{self.max_balance_drawdown_percent}%"
            )

        new_state = DrawdownState(
            equity_high_watermark=eq_hwm,
            balance_high_watermark=bal_hwm,
            current_equity_drawdown=eq_dd,
            current_balance_drawdown=bal_dd,
            max_equity_drawdown_ever=max_eq_dd,
            max_balance_drawdown_ever=max_bal_dd,
            updated_at=now,
        )
        self._state = new_state

        return DrawdownResult(
            equity_drawdown_percent=eq_dd,
            balance_drawdown_percent=bal_dd,
            equity_high_watermark=eq_hwm,
            balance_high_watermark=bal_hwm,
            max_equity_drawdown_ever=max_eq_dd,
            max_balance_drawdown_ever=max_bal_dd,
            within_equity_limit=within_eq,
            within_balance_limit=within_bal,
            limit_breach_reasons=reasons,
            state=new_state,
        )

    @staticmethod
    def _drawdown(high_watermark: Decimal, current: Decimal) -> Decimal:
        if high_watermark <= 0:
            return Decimal("0")
        dd = high_watermark - current
        if dd <= 0:
            return Decimal("0")
        return dd / high_watermark * Decimal("100")

    def persist(self, path: str) -> None:
        """Persist drawdown state to a JSON file (safe, append-only-ish)."""
        payload = {
            "equity_high_watermark": str(self._state.equity_high_watermark),
            "balance_high_watermark": str(self._state.balance_high_watermark),
            "max_equity_drawdown_ever": str(self._state.max_equity_drawdown_ever),
            "max_balance_drawdown_ever": str(self._state.max_balance_drawdown_ever),
            "updated_at": (
                self._state.updated_at.isoformat()
                if self._state.updated_at else None
            ),
        }
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp, path)

    @classmethod
    def load(
        cls,
        path: str,
        max_equity_drawdown_percent: Decimal,
        max_balance_drawdown_percent: Decimal,
    ) -> "DrawdownTracker":
        """Load persisted drawdown state. Fails safely (zero state) if missing."""
        tracker = cls(
            max_equity_drawdown_percent=max_equity_drawdown_percent,
            max_balance_drawdown_percent=max_balance_drawdown_percent,
        )
        if not os.path.isfile(path):
            return tracker
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            eq_hwm = Decimal(data.get("equity_high_watermark", "0"))
            bal_hwm = Decimal(data.get("balance_high_watermark", "0"))
            max_eq = Decimal(data.get("max_equity_drawdown_ever", "0"))
            max_bal = Decimal(data.get("max_balance_drawdown_ever", "0"))
            updated_at = data.get("updated_at")
            dt = None
            if updated_at:
                dt = datetime.fromisoformat(updated_at)
            tracker._state = DrawdownState(
                equity_high_watermark=eq_hwm,
                balance_high_watermark=bal_hwm,
                current_equity_drawdown=Decimal("0"),
                current_balance_drawdown=Decimal("0"),
                max_equity_drawdown_ever=max_eq,
                max_balance_drawdown_ever=max_bal,
                updated_at=dt,
            )
        except (OSError, ValueError, KeyError):
            # Corrupt or unreadable state: fail safely with zero watermarks.
            pass
        return tracker
