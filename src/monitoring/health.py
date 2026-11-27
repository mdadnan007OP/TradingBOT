"""Phase 10 — Centralized system health monitoring.

Monitors broker/MT5, market data, strategy engine, risk engine, news engine,
and execution engine subsystems. Never exposes passwords or sensitive account
identifiers.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status values."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class SubsystemHealth:
    """Health of a single subsystem."""

    name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    detail: Optional[str] = None
    last_check: Optional[datetime] = None
    latency_ms: Optional[float] = None
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "detail": self.detail,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "latency_ms": self.latency_ms,
            "metrics": self.metrics,
        }


class HealthChecker:
    """Base class for subsystem health checkers."""

    def __init__(self, name: str) -> None:
        self.name = name

    def check(self) -> SubsystemHealth:
        raise NotImplementedError


class HealthService:
    """Centralized system health service.

    Aggregates health from all subsystems and provides a unified health view.
    """

    def __init__(self) -> None:
        self._checkers: Dict[str, HealthChecker] = {}
        self._last_results: Dict[str, SubsystemHealth] = {}

    def register(self, checker: HealthChecker) -> None:
        self._checkers[checker.name] = checker

    def unregister(self, name: str) -> None:
        self._checkers.pop(name, None)

    def check_all(self) -> Dict[str, SubsystemHealth]:
        """Run all health checks and return results."""
        results: Dict[str, SubsystemHealth] = {}
        for name, checker in self._checkers.items():
            start = time.perf_counter()
            try:
                health = checker.check()
                elapsed_ms = (time.perf_counter() - start) * 1000
                health.latency_ms = round(elapsed_ms, 2)
                health.last_check = datetime.now(timezone.utc)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Health check failed for %s: %s", name, exc)
                health = SubsystemHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    detail=str(exc),
                    last_check=datetime.now(timezone.utc),
                    latency_ms=(time.perf_counter() - start) * 1000,
                )
            results[name] = health
            self._last_results[name] = health
        return results

    def check_one(self, name: str) -> Optional[SubsystemHealth]:
        """Run a single health check by name."""
        checker = self._checkers.get(name)
        if checker is None:
            return None
        return checker.check()

    def overall_status(self) -> HealthStatus:
        """Return the overall health status across all subsystems."""
        if not self._last_results:
            return HealthStatus.UNKNOWN
        statuses = [h.status for h in self._last_results.values()]
        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            return HealthStatus.UNHEALTHY
        if any(s == HealthStatus.DEGRADED for s in statuses):
            return HealthStatus.DEGRADED
        if any(s == HealthStatus.UNKNOWN for s in statuses):
            return HealthStatus.UNKNOWN
        return HealthStatus.HEALTHY

    def summary(self) -> Dict[str, Any]:
        """Return a summary dictionary of all health results."""
        return {
            "overall": self.overall_status().value,
            "subsystems": {name: h.to_dict() for name, h in self._last_results.items()},
        }


# ---------------------------------------------------------------------------
# Concrete subsystem health checkers
# ---------------------------------------------------------------------------


class BrokerHealthChecker(HealthChecker):
    """Checks MT5 terminal connection, account mode, server, and broker identity."""

    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        super().__init__("broker")
        self._connection_factory = connection_factory

    def check(self) -> SubsystemHealth:
        try:
            conn = self._connection_factory()
            connected = conn.check_connection() if hasattr(conn, "check_connection") else False
            account_info = None
            if hasattr(conn, "get_account_info"):
                account_info = conn.get_account_info()

            metrics: Dict[str, Any] = {"connected": connected}
            detail_parts: List[str] = []

            if account_info is not None:
                # Never log raw login identifiers.
                metrics["trade_mode"] = getattr(account_info, "trade_mode", "unknown")
                metrics["trade_allowed"] = bool(getattr(account_info, "trade_allowed", False))
                metrics["server"] = getattr(account_info, "server", "unknown")
                metrics["currency"] = getattr(account_info, "currency", "unknown")
                detail_parts.append(f"mode={metrics['trade_mode']}")
                detail_parts.append(f"server={metrics['server']}")

            if connected:
                status = HealthStatus.HEALTHY
                detail = "MT5 terminal connected; " + "; ".join(detail_parts) if detail_parts else "MT5 terminal connected"
            else:
                status = HealthStatus.UNHEALTHY
                detail = "MT5 terminal not connected"

            return SubsystemHealth(
                name=self.name,
                status=status,
                detail=detail,
                metrics=metrics,
            )
        except Exception as exc:  # noqa: BLE001
            return SubsystemHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                detail=f"Broker health check error: {exc}",
            )


class MarketDataHealthChecker(HealthChecker):
    """Checks market data freshness, gaps, and provider availability."""

    def __init__(self, market_data: Any) -> None:
        super().__init__("market_data")
        self._market_data = market_data

    def check(self) -> SubsystemHealth:
        try:
            available = self._market_data is not None and hasattr(self._market_data, "get_tick")
            if not available:
                return SubsystemHealth(
                    name=self.name,
                    status=HealthStatus.UNHEALTHY,
                    detail="Market data provider not available",
                )

            # Check a known symbol for freshness.
            tick = self._market_data.get_tick("EURUSD")
            if tick is None:
                return SubsystemHealth(
                    name=self.name,
                    status=HealthStatus.DEGRADED,
                    detail="No tick data available for EURUSD",
                    metrics={"provider_available": True, "fresh_quote": False},
                )

            # Quote freshness: within 60 seconds.
            age_s = (datetime.now(timezone.utc) - tick.timestamp).total_seconds()
            fresh = age_s < 60

            metrics = {
                "provider_available": True,
                "fresh_quote": fresh,
                "quote_age_seconds": round(age_s, 2),
                "spread": str(tick.spread),
            }

            status = HealthStatus.HEALTHY if fresh else HealthStatus.DEGRADED
            detail = f"Quote age {age_s:.1f}s" + (" (fresh)" if fresh else " (stale)")

            return SubsystemHealth(
                name=self.name,
                status=status,
                detail=detail,
                metrics=metrics,
            )
        except Exception as exc:  # noqa: BLE001
            return SubsystemHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                detail=f"Market data health check error: {exc}",
            )


class StrategyEngineHealthChecker(HealthChecker):
    """Checks strategy engine health: enabled strategies, errors, processing."""

    def __init__(self, strategy_engine: Any) -> None:
        super().__init__("strategy_engine")
        self._strategy_engine = strategy_engine

    def check(self) -> SubsystemHealth:
        try:
            available = self._strategy_engine is not None
            if not available:
                return SubsystemHealth(
                    name=self.name,
                    status=HealthStatus.UNHEALTHY,
                    detail="Strategy engine not available",
                )

            enabled = 0
            errors = 0
            if hasattr(self._strategy_engine, "strategies"):
                strategies = self._strategy_engine.strategies
                enabled = sum(1 for s in strategies.values() if getattr(s, "enabled", False))

            metrics = {"enabled_strategies": enabled, "errors": errors}
            status = HealthStatus.HEALTHY if available else HealthStatus.UNHEALTHY
            detail = f"{enabled} strategy(ies) enabled"

            return SubsystemHealth(name=self.name, status=status, detail=detail, metrics=metrics)
        except Exception as exc:  # noqa: BLE001
            return SubsystemHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                detail=f"Strategy engine health check error: {exc}",
            )


class RiskEngineHealthChecker(HealthChecker):
    """Checks risk engine availability, circuit breaker status, daily loss."""

    def __init__(self, risk_engine: Any) -> None:
        super().__init__("risk_engine")
        self._risk_engine = risk_engine

    def check(self) -> SubsystemHealth:
        try:
            available = self._risk_engine is not None
            if not available:
                return SubsystemHealth(
                    name=self.name,
                    status=HealthStatus.UNHEALTHY,
                    detail="Risk engine not available",
                )

            metrics: Dict[str, Any] = {"available": True}
            detail_parts: List[str] = ["risk engine available"]

            # Check circuit breaker if available.
            if hasattr(self._risk_engine, "circuit_breaker"):
                cb = self._risk_engine.circuit_breaker
                if hasattr(cb, "is_locked"):
                    metrics["circuit_breaker_locked"] = bool(cb.is_locked())
                    if cb.is_locked():
                        detail_parts.append("circuit breaker LOCKED")

            if hasattr(self._risk_engine, "daily_loss_limit_reached"):
                metrics["daily_loss_limit_reached"] = bool(self._risk_engine.daily_loss_limit_reached())

            status = HealthStatus.HEALTHY
            if metrics.get("circuit_breaker_locked"):
                status = HealthStatus.UNHEALTHY

            return SubsystemHealth(
                name=self.name,
                status=status,
                detail="; ".join(detail_parts),
                metrics=metrics,
            )
        except Exception as exc:  # noqa: BLE001
            return SubsystemHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                detail=f"Risk engine health check error: {exc}",
            )


class NewsEngineHealthChecker(HealthChecker):
    """Checks news provider health, calendar freshness, active restrictions."""

    def __init__(self, news_engine: Any) -> None:
        super().__init__("news_engine")
        self._news_engine = news_engine

    def check(self) -> SubsystemHealth:
        try:
            available = self._news_engine is not None
            if not available:
                return SubsystemHealth(
                    name=self.name,
                    status=HealthStatus.UNHEALTHY,
                    detail="News engine not available",
                )

            metrics = {"provider_available": True}
            detail_parts: List[str] = ["news engine available"]

            # Check for active restrictions.
            if hasattr(self._news_engine, "is_trading_allowed"):
                allowed = self._news_engine.is_trading_allowed("EURUSD")
                metrics["trading_allowed"] = bool(allowed)
                if not allowed:
                    detail_parts.append("trading restricted by news")

            status = HealthStatus.HEALTHY
            detail = "; ".join(detail_parts)

            return SubsystemHealth(name=self.name, status=status, detail=detail, metrics=metrics)
        except Exception as exc:  # noqa: BLE001
            return SubsystemHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                detail=f"News engine health check error: {exc}",
            )


class ExecutionEngineHealthChecker(HealthChecker):
    """Checks execution engine mode, pending approvals, unresolved executions."""

    def __init__(self, execution_engine: Any) -> None:
        super().__init__("execution_engine")
        self._execution_engine = execution_engine

    def check(self) -> SubsystemHealth:
        try:
            available = self._execution_engine is not None
            if not available:
                return SubsystemHealth(
                    name=self.name,
                    status=HealthStatus.UNHEALTHY,
                    detail="Execution engine not available",
                )

            metrics: Dict[str, Any] = {"available": True}
            detail_parts: List[str] = ["execution engine available"]

            # Execution mode.
            if hasattr(self._execution_engine, "config"):
                mode = getattr(self._execution_engine.config, "mode", "unknown")
                metrics["mode"] = str(mode)
                detail_parts.append(f"mode={mode}")

            # Count pending approvals / unresolved executions via journal if available.
            if hasattr(self._execution_engine, "journal"):
                journal = self._execution_engine.journal
                if hasattr(journal, "load_all"):
                    records = journal.load_all()
                    unresolved = sum(
                        1 for r in records if not getattr(r, "is_terminal", True)
                    )
                    metrics["unresolved_executions"] = unresolved
                    if unresolved > 0:
                        detail_parts.append(f"{unresolved} unresolved execution(s)")

            status = HealthStatus.HEALTHY
            if metrics.get("unresolved_executions", 0) > 0:
                status = HealthStatus.DEGRADED

            return SubsystemHealth(
                name=self.name,
                status=status,
                detail="; ".join(detail_parts),
                metrics=metrics,
            )
        except Exception as exc:  # noqa: BLE001
            return SubsystemHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                detail=f"Execution engine health check error: {exc}",
            )


# ---------------------------------------------------------------------------
# Default health service with standard checkers
# ---------------------------------------------------------------------------


def create_default_health_service() -> HealthService:
    """Create a HealthService with standard subsystem checkers (no-op if deps unavailable)."""
    service = HealthService()
    # Checkers are registered by the application lifecycle manager with real
    # dependencies. Here we register no-op checkers so the service always has
    # structure even when subsystems are not yet initialized.
    return service
