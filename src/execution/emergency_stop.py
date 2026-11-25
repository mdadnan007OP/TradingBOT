"""Phase 9 execution circuit breakers.

Independent execution-level protections in addition to Phase 6 risk controls.
All states are persisted and survive application restarts.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class CircuitBreakerState:
    active: bool = False
    reason: Optional[str] = None
    triggered_at: Optional[datetime] = None
    lockout_until: Optional[datetime] = None
    audit_history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class EmergencyControls:
    global_execution_lock: bool = False
    new_entry_emergency_stop: bool = False
    max_demo_orders_per_day: int = 0
    max_simultaneous_positions: int = 0
    max_per_order_volume: Decimal = Decimal("0")
    max_daily_monetary_risk: Decimal = Decimal("0")
    connection_loss_lockout: bool = False
    account_identity_change_lockout: bool = False
    risk_engine_failure_lockout: bool = False
    news_engine_unavailable_lockout: bool = False
    stale_quote_lockout: bool = False
    unexpected_position_lockout: bool = False
    reconciliation_failure_lockout: bool = False
    audit_history: list = field(default_factory=list)

    def is_any_lockout_active(self) -> bool:
        return any(
            getattr(self, name)
            for name in (
                "global_execution_lock",
                "new_entry_emergency_stop",
                "connection_loss_lockout",
                "account_identity_change_lockout",
                "risk_engine_failure_lockout",
                "news_engine_unavailable_lockout",
                "stale_quote_lockout",
                "unexpected_position_lockout",
                "reconciliation_failure_lockout",
            )
        )


class EmergencyStop:
    """Manages persistent execution circuit breakers."""

    def __init__(self, directory: str = ".emergency_stop") -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "breakers.json"
        self.state = self._load()

    def _load(self) -> EmergencyControls:
        if not self.path.exists():
            return EmergencyControls()
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return EmergencyControls(
                global_execution_lock=bool(data.get("global_execution_lock", False)),
                new_entry_emergency_stop=bool(data.get("new_entry_emergency_stop", False)),
                max_demo_orders_per_day=int(data.get("max_demo_orders_per_day", 0)),
                max_simultaneous_positions=int(data.get("max_simultaneous_positions", 0)),
                max_per_order_volume=self._dec(data.get("max_per_order_volume", "0")),
                max_daily_monetary_risk=self._dec(data.get("max_daily_monetary_risk", "0")),
                connection_loss_lockout=bool(data.get("connection_loss_lockout", False)),
                account_identity_change_lockout=bool(data.get("account_identity_change_lockout", False)),
                risk_engine_failure_lockout=bool(data.get("risk_engine_failure_lockout", False)),
                news_engine_unavailable_lockout=bool(data.get("news_engine_unavailable_lockout", False)),
                stale_quote_lockout=bool(data.get("stale_quote_lockout", False)),
                unexpected_position_lockout=bool(data.get("unexpected_position_lockout", False)),
                reconciliation_failure_lockout=bool(data.get("reconciliation_failure_lockout", False)),
            )
        except (OSError, ValueError):
            return EmergencyControls()

    def _save(self) -> None:
        data = {
            "global_execution_lock": self.state.global_execution_lock,
            "new_entry_emergency_stop": self.state.new_entry_emergency_stop,
            "max_demo_orders_per_day": self.state.max_demo_orders_per_day,
            "max_simultaneous_positions": self.state.max_simultaneous_positions,
            "max_per_order_volume": str(self.state.max_per_order_volume),
            "max_daily_monetary_risk": str(self.state.max_daily_monetary_risk),
            "connection_loss_lockout": self.state.connection_loss_lockout,
            "account_identity_change_lockout": self.state.account_identity_change_lockout,
            "risk_engine_failure_lockout": self.state.risk_engine_failure_lockout,
            "news_engine_unavailable_lockout": self.state.news_engine_unavailable_lockout,
            "stale_quote_lockout": self.state.stale_quote_lockout,
            "unexpected_position_lockout": self.state.unexpected_position_lockout,
            "reconciliation_failure_lockout": self.state.reconciliation_failure_lockout,
        }
        tmp = str(self.path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, self.path)

    @staticmethod
    def _dec(value: Any) -> Decimal:
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0")

    def is_execution_blocked(self) -> bool:
        return (
            self.state.global_execution_lock
            or self.state.new_entry_emergency_stop
            or self.state.is_any_lockout_active()
        )

    def activate_global_lock(self, reason: str = "manual") -> None:
        self.state.global_execution_lock = True
        self._record(reason)
        self._save()

    def deactivate_global_lock(self) -> None:
        self.state.global_execution_lock = False
        self._save()

    def activate_new_entry_stop(self, reason: str = "manual") -> None:
        self.state.new_entry_emergency_stop = True
        self._record(reason)
        self._save()

    def deactivate_new_entry_stop(self) -> None:
        self.state.new_entry_emergency_stop = False
        self._save()

    def set_connection_loss(self, active: bool) -> None:
        self.state.connection_loss_lockout = active
        self._save()

    def set_account_identity_change(self, active: bool) -> None:
        self.state.account_identity_change_lockout = active
        self._save()

    def set_risk_engine_failure(self, active: bool) -> None:
        self.state.risk_engine_failure_lockout = active
        self._save()

    def set_news_unavailable(self, active: bool) -> None:
        self.state.news_engine_unavailable_lockout = active
        self._save()

    def set_stale_quote(self, active: bool) -> None:
        self.state.stale_quote_lockout = active
        self._save()

    def set_reconciliation_failure(self, active: bool) -> None:
        self.state.reconciliation_failure_lockout = active
        self._save()

    def check_daily_order_limit(self, orders_today: int) -> bool:
        limit = self.state.max_demo_orders_per_day
        if limit > 0 and orders_today >= limit:
            return True
        return False

    def check_position_limit(self, open_positions: int) -> bool:
        limit = self.state.max_simultaneous_positions
        if limit > 0 and open_positions >= limit:
            return True
        return False

    def check_order_volume(self, volume: Decimal) -> bool:
        limit = self.state.max_per_order_volume
        if limit > 0 and volume > limit:
            return True
        return False

    def _record(self, reason: str) -> None:
        self.state.audit_history.append(
            {
                "reason": reason,
                "triggered_at": datetime.now(timezone.utc).isoformat(),
            }
        )
