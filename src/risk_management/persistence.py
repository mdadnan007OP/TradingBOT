"""Safe persistence for risk-protection state.

Persists circuit-breaker and drawdown state so application restarts cannot
accidentally reset protection limits. Uses atomic write (tmp + replace).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, Optional

from src.risk_management.base import CircuitBreakerState
from src.risk_management.models import DailyPnLState, DrawdownState


def _atomic_write(path: str, payload: Dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    os.replace(tmp, path)


def save_circuit_breaker(path: str, state: CircuitBreakerState) -> None:
    payload = {
        "active": state.active,
        "reason": state.reason.value if state.reason else None,
        "triggered_at": state.triggered_at.isoformat() if state.triggered_at else None,
        "lockout_until": state.lockout_until.isoformat() if state.lockout_until else None,
        "reset_required": state.reset_required,
        "audit_history": state.audit_history,
    }
    _atomic_write(path, payload)


def load_circuit_breaker(path: str) -> CircuitBreakerState:
    from src.risk_management.base import CircuitBreakerReason

    if not os.path.isfile(path):
        return CircuitBreakerState()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        reason = None
        if data.get("reason"):
            reason = CircuitBreakerReason(data["reason"])

        def _dt(key):
            v = data.get(key)
            return datetime.fromisoformat(v) if v else None

        return CircuitBreakerState(
            active=data.get("active", False),
            reason=reason,
            triggered_at=_dt("triggered_at"),
            lockout_until=_dt("lockout_until"),
            reset_required=data.get("reset_required", True),
            audit_history=data.get("audit_history", []),
        )
    except (OSError, ValueError, KeyError):
        return CircuitBreakerState()


def save_drawdown(path: str, state: DrawdownState) -> None:
    payload = {
        "equity_high_watermark": str(state.equity_high_watermark),
        "balance_high_watermark": str(state.balance_high_watermark),
        "current_equity_drawdown": str(state.current_equity_drawdown),
        "current_balance_drawdown": str(state.current_balance_drawdown),
        "max_equity_drawdown_ever": str(state.max_equity_drawdown_ever),
        "max_balance_drawdown_ever": str(state.max_balance_drawdown_ever),
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }
    _atomic_write(path, payload)


def load_drawdown(path: str) -> DrawdownState:
    if not os.path.isfile(path):
        return DrawdownState(
            equity_high_watermark=Decimal("0"),
            balance_high_watermark=Decimal("0"),
        )
    try:
        from decimal import Decimal
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        def _dec(key, default="0"):
            return Decimal(str(data.get(key, default)))

        updated_at = data.get("updated_at")
        dt = datetime.fromisoformat(updated_at) if updated_at else None
        return DrawdownState(
            equity_high_watermark=_dec("equity_high_watermark"),
            balance_high_watermark=_dec("balance_high_watermark"),
            current_equity_drawdown=_dec("current_equity_drawdown"),
            current_balance_drawdown=_dec("current_balance_drawdown"),
            max_equity_drawdown_ever=_dec("max_equity_drawdown_ever"),
            max_balance_drawdown_ever=_dec("max_balance_drawdown_ever"),
            updated_at=dt,
        )
    except (OSError, ValueError, KeyError):
        return DrawdownState(
            equity_high_watermark=Decimal("0"),
            balance_high_watermark=Decimal("0"),
        )


def save_daily_pnl(path: str, state: DailyPnLState) -> None:
    payload = {
        "starting_balance": str(state.starting_balance),
        "starting_equity": str(state.starting_equity),
        "realized_pnl": str(state.realized_pnl),
        "unrealized_pnl": str(state.unrealized_pnl),
        "deposits": str(state.deposits),
        "withdrawals": str(state.withdrawals),
        "date": state.date,
        "trading_locked": state.trading_locked,
        "locked_at": state.locked_at.isoformat() if state.locked_at else None,
    }
    _atomic_write(path, payload)


def load_daily_pnl(path: str) -> DailyPnLState:
    from decimal import Decimal

    if not os.path.isfile(path):
        return DailyPnLState(
            starting_balance=Decimal("0"),
            starting_equity=Decimal("0"),
        )
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        def _dec(key, default="0"):
            return Decimal(str(data.get(key, default)))

        locked_at = data.get("locked_at")
        dt = datetime.fromisoformat(locked_at) if locked_at else None
        return DailyPnLState(
            starting_balance=_dec("starting_balance"),
            starting_equity=_dec("starting_equity"),
            realized_pnl=_dec("realized_pnl"),
            unrealized_pnl=_dec("unrealized_pnl"),
            deposits=_dec("deposits"),
            withdrawals=_dec("withdrawals"),
            date=data.get("date"),
            trading_locked=data.get("trading_locked", False),
            locked_at=dt,
        )
    except (OSError, ValueError, KeyError):
        return DailyPnLState(
            starting_balance=Decimal("0"),
            starting_equity=Decimal("0"),
        )
