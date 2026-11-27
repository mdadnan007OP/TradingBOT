"""Phase 10 — Heartbeat and watchdog mechanism.

Every critical subsystem reports heartbeat status. The watchdog detects
freezes, disconnects, stalls, and service unavailability using configurable
timeouts.

The watchdog must never automatically authorize new trading.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class HeartbeatStatus(str, Enum):
    """Heartbeat status values."""

    ALIVE = "alive"
    STALE = "stale"
    DEAD = "dead"
    UNKNOWN = "unknown"


@dataclass
class HeartbeatRecord:
    """A single heartbeat report from a subsystem."""

    name: str
    status: HeartbeatStatus = HeartbeatStatus.UNKNOWN
    last_successful_operation: Optional[datetime] = None
    last_heartbeat_time: Optional[datetime] = None
    failure_count: int = 0
    processing_latency_ms: Optional[float] = None
    last_error: Optional[str] = None

    def is_stale(self, timeout_seconds: float) -> bool:
        if self.last_heartbeat_time is None:
            return True
        age = (datetime.now(timezone.utc) - self.last_heartbeat_time).total_seconds()
        return age > timeout_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "last_successful_operation": (
                self.last_successful_operation.isoformat() if self.last_successful_operation else None
            ),
            "last_heartbeat_time": (
                self.last_heartbeat_time.isoformat() if self.last_heartbeat_time else None
            ),
            "failure_count": self.failure_count,
            "processing_latency_ms": self.processing_latency_ms,
            "last_error": self.last_error,
        }


class HeartbeatReporter:
    """Reports heartbeat status for a single subsystem."""

    def __init__(self, name: str, registry: "HeartbeatRegistry") -> None:
        self.name = name
        self._registry = registry

    def report(
        self,
        *,
        status: HeartbeatStatus = HeartbeatStatus.ALIVE,
        last_successful_operation: Optional[datetime] = None,
        processing_latency_ms: Optional[float] = None,
        last_error: Optional[str] = None,
        failure_count: int = 0,
    ) -> None:
        self._registry.update(
            name=self.name,
            status=status,
            last_successful_operation=last_successful_operation,
            last_heartbeat_time=datetime.now(timezone.utc),
            processing_latency_ms=processing_latency_ms,
            last_error=last_error,
            failure_count=failure_count,
        )

    def success(self, processing_latency_ms: Optional[float] = None) -> None:
        """Report a successful heartbeat."""
        self.report(
            status=HeartbeatStatus.ALIVE,
            last_successful_operation=datetime.now(timezone.utc),
            processing_latency_ms=processing_latency_ms,
            last_error=None,
            failure_count=0,
        )

    def failure(self, error: str, processing_latency_ms: Optional[float] = None) -> None:
        """Report a failed heartbeat."""
        record = self._registry._records.get(self.name)
        current_failures = record.failure_count if record else 0
        self.report(
            status=HeartbeatStatus.DEAD,
            last_error=error,
            processing_latency_ms=processing_latency_ms,
            failure_count=current_failures + 1,
        )


class HeartbeatRegistry:
    """Central registry of all subsystem heartbeats."""

    def __init__(self) -> None:
        self._records: Dict[str, HeartbeatRecord] = {}

    def update(
        self,
        *,
        name: str,
        status: HeartbeatStatus,
        last_successful_operation: Optional[datetime],
        last_heartbeat_time: datetime,
        processing_latency_ms: Optional[float],
        last_error: Optional[str],
        failure_count: int,
    ) -> None:
        self._records[name] = HeartbeatRecord(
            name=name,
            status=status,
            last_successful_operation=last_successful_operation,
            last_heartbeat_time=last_heartbeat_time,
            processing_latency_ms=processing_latency_ms,
            last_error=last_error,
            failure_count=failure_count,
        )

    def get(self, name: str) -> Optional[HeartbeatRecord]:
        return self._records.get(name)

    def all(self) -> Dict[str, HeartbeatRecord]:
        return dict(self._records)

    def stale_subsystems(self, timeout_seconds: float) -> List[str]:
        """Return names of subsystems whose heartbeats are stale."""
        stale: List[str] = []
        for name, record in self._records.items():
            if record.is_stale(timeout_seconds):
                stale.append(name)
        return stale

    def to_dict(self) -> Dict[str, Any]:
        return {name: r.to_dict() for name, r in self._records.items()}


class Watchdog:
    """Watchdog that detects system freezes, disconnects, stalls, and
    service unavailability using configurable timeouts.

    The watchdog never automatically authorizes new trading.
    """

    def __init__(
        self,
        registry: HeartbeatRegistry,
        *,
        heartbeat_timeout_seconds: float = 30.0,
        market_data_stale_seconds: float = 60.0,
        mt5_disconnect_timeout_seconds: float = 30.0,
        block_execution_on_unavailable_risk: bool = True,
        block_execution_on_unavailable_identity: bool = True,
        block_execution_on_unavailable_reconciliation: bool = True,
    ) -> None:
        self._registry = registry
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self.market_data_stale_seconds = market_data_stale_seconds
        self.mt5_disconnect_timeout_seconds = mt5_disconnect_timeout_seconds
        self.block_execution_on_unavailable_risk = block_execution_on_unavailable_risk
        self.block_execution_on_unavailable_identity = block_execution_on_unavailable_identity
        self.block_execution_on_unavailable_reconciliation = block_execution_on_unavailable_reconciliation
        self._last_check: Optional[datetime] = None
        self._alerts: List[str] = []

    def check(self) -> Dict[str, Any]:
        """Run watchdog checks and return a status report.

        Never automatically authorizes new trading.
        """
        self._last_check = datetime.now(timezone.utc)
        self._alerts = []

        issues: List[str] = []
        block_execution = False

        # Check all subsystems for stale heartbeats.
        stale = self._registry.stale_subsystems(self.heartbeat_timeout_seconds)
        for name in stale:
            issues.append(f"Heartbeat stale: {name}")
            block_execution = True

        # Market data specific staleness.
        market_record = self._registry.get("market_data")
        if market_record and market_record.is_stale(self.market_data_stale_seconds):
            issues.append("Market data stalled")
            block_execution = True

        # MT5 disconnect check.
        broker_record = self._registry.get("broker")
        if broker_record and broker_record.is_stale(self.mt5_disconnect_timeout_seconds):
            issues.append("MT5 disconnection detected")
            block_execution = True

        # Risk engine availability.
        risk_record = self._registry.get("risk_engine")
        if self.block_execution_on_unavailable_risk:
            if risk_record is None or risk_record.status == HeartbeatStatus.DEAD:
                issues.append("Risk engine unavailable - blocking new demo execution")
                block_execution = True

        # Account identity availability.
        identity_record = self._registry.get("account_identity")
        if self.block_execution_on_unavailable_identity:
            if identity_record is None or identity_record.status == HeartbeatStatus.DEAD:
                issues.append("Account identity service unavailable - blocking new demo execution")
                block_execution = True

        # Reconciliation availability.
        recon_record = self._registry.get("reconciliation")
        if self.block_execution_on_unavailable_reconciliation:
            if recon_record is None or recon_record.status == HeartbeatStatus.DEAD:
                issues.append("Execution reconciliation unavailable - blocking new demo execution")
                block_execution = True

        self._alerts = issues

        return {
            "checked_at": self._last_check.isoformat(),
            "issues": issues,
            "block_execution": block_execution,
            "subsystems": self._registry.to_dict(),
        }

    def has_issues(self) -> bool:
        return len(self._alerts) > 0

    def get_alerts(self) -> List[str]:
        return list(self._alerts)

    def should_block_execution(self) -> bool:
        """Return True if the watchdog recommends blocking new trading."""
        result = self.check()
        return result["block_execution"]
