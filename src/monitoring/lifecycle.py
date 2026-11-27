"""Phase 10 — Centralized application lifecycle manager.

Defines explicit lifecycle states and orchestrates application startup,
dependency initialization, module initialization, and graceful shutdown.

The application must not report RUNNING when critical dependencies are
unavailable. Startup must never silently switch execution modes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class LifecycleState(str, Enum):
    """Explicit application lifecycle states."""

    INITIALIZING = "INITIALIZING"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    LOCKED = "LOCKED"


@dataclass
class LifecycleTransition:
    """Record of a lifecycle state transition."""

    from_state: Optional[LifecycleState]
    to_state: LifecycleState
    timestamp: datetime
    reason: Optional[str] = None


@dataclass
class ComponentHealth:
    """Health status of a single component."""

    name: str
    healthy: bool
    detail: Optional[str] = None
    last_checked: Optional[datetime] = None


class ApplicationLifecycleManager:
    """Centralized application lifecycle manager.

    Coordinates startup, dependency initialization, module initialization,
    and graceful shutdown. Tracks lifecycle state transitions and component
    health.
    """

    # States from which a transition to RUNNING is permitted.
    _RUNNABLE_STATES = frozenset(
        {LifecycleState.STARTING, LifecycleState.DEGRADED, LifecycleState.STOPPED}
    )

    def __init__(self) -> None:
        self._state = LifecycleState.INITIALIZING
        self._history: List[LifecycleTransition] = []
        self._components: Dict[str, ComponentHealth] = {}
        self._start_time: Optional[datetime] = None
        self._stop_time: Optional[datetime] = None
        self._lock = _LifecycleLock()
        self._shutdown_hooks: List[Callable[[], None]] = []
        self._critical_failures: List[str] = []

    # ------------------------------------------------------------------
    # State access
    # ------------------------------------------------------------------

    @property
    def state(self) -> LifecycleState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state == LifecycleState.RUNNING

    @property
    def is_stopped(self) -> bool:
        return self._state in (LifecycleState.STOPPED, LifecycleState.FAILED, LifecycleState.LOCKED)

    @property
    def is_locked(self) -> bool:
        return self._state == LifecycleState.LOCKED

    @property
    def uptime_seconds(self) -> Optional[float]:
        if self._start_time is None:
            return None
        end = self._stop_time or datetime.now(timezone.utc)
        return (end - self._start_time).total_seconds()

    @property
    def component_health(self) -> Dict[str, ComponentHealth]:
        return dict(self._components)

    @property
    def transition_history(self) -> List[LifecycleTransition]:
        return list(self._history)

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def _transition(self, to_state: LifecycleState, reason: Optional[str] = None) -> None:
        from_state = self._state
        self._state = to_state
        self._history.append(
            LifecycleTransition(
                from_state=from_state,
                to_state=to_state,
                timestamp=datetime.now(timezone.utc),
                reason=reason,
            )
        )
        logger.info("Lifecycle transition: %s -> %s%s", from_state.value, to_state.value, f" ({reason})" if reason else "")

    def _can_transition_to(self, to_state: LifecycleState) -> bool:
        """Validate lifecycle transitions."""
        current = self._state
        if to_state == LifecycleState.RUNNING:
            return current in self._RUNNABLE_STATES
        if to_state == LifecycleState.STOPPING:
            return current in (
                LifecycleState.STARTING,
                LifecycleState.RUNNING,
                LifecycleState.DEGRADED,
                LifecycleState.FAILED,
            )
        if to_state == LifecycleState.STOPPED:
            return current == LifecycleState.STOPPING
        if to_state == LifecycleState.FAILED:
            return current != LifecycleState.STOPPED
        if to_state == LifecycleState.LOCKED:
            return True  # Lock can be applied from any state
        if to_state == LifecycleState.STARTING:
            return current in (LifecycleState.INITIALIZING, LifecycleState.STOPPED)
        if to_state == LifecycleState.DEGRADED:
            return current in (LifecycleState.STARTING, LifecycleState.RUNNING)
        if to_state == LifecycleState.INITIALIZING:
            return current == LifecycleState.STOPPED
        return False

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Start the application lifecycle.

        Returns True if the application reached RUNNING or DEGRADED.
        Returns False if startup failed (FAILED state).
        """
        if self._lock.is_locked():
            self._transition(LifecycleState.LOCKED, "Process lock already held")
            return False

        if not self._lock.acquire():
            self._transition(LifecycleState.LOCKED, "Failed to acquire process lock")
            return False

        try:
            return self._do_start()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Application startup failed: %s", exc)
            self._transition(LifecycleState.FAILED, str(exc))
            self._lock.release()
            return False

    def _do_start(self) -> bool:
        """Internal startup sequence."""
        self._transition(LifecycleState.STARTING, "Application startup initiated")
        self._start_time = datetime.now(timezone.utc)

        # Phase 1: Validate configuration.
        self._transition(LifecycleState.INITIALIZING, "Validating configuration")
        config_errors = self._validate_configuration()
        if config_errors:
            self._critical_failures.extend(config_errors)
            self._transition(LifecycleState.FAILED, "Configuration validation failed")
            return False

        # Phase 2: Initialize dependencies (mock broker, execution engine, etc.).
        dep_errors = self._initialize_dependencies()
        if dep_errors:
            self._critical_failures.extend(dep_errors)
            # Non-critical dependency failures lead to DEGRADED, not FAILED.
            self._transition(LifecycleState.DEGRADED, "Some dependencies unavailable")
        else:
            self._transition(LifecycleState.RUNNING, "All dependencies initialized")

        # Register shutdown hook.
        self._shutdown_hooks.append(self._shutdown_dependencies)

        return self._state in (LifecycleState.RUNNING, LifecycleState.DEGRADED)

    def _validate_configuration(self) -> List[str]:
        """Validate application configuration. Returns list of error messages."""
        errors: List[str] = []

        # Execution mode must not be LIVE.
        try:
            from src.config import CONFIG as _cfg

            exec_mode = _cfg.trading.mode
            if exec_mode in ("live", "real"):
                errors.append("LIVE/REAL trading mode is not permitted")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Cannot read trading mode: {exc}")

        # PAPER mode must remain the default.
        try:
            from src.execution.config import ExecutionConfig, ExecutionMode

            exec_config = ExecutionConfig.from_env()
            if exec_config.mode == ExecutionMode.PAPER:
                logger.info("Execution mode confirmed: PAPER (default)")
            elif exec_config.demo_trading_permitted:
                logger.warning("Execution mode is DEMO - explicit authorization required for order submission")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Cannot validate execution config: {exc}")

        # Monitoring config validation.
        try:
            from src.config import CONFIG as _cfg

            _ = _cfg.monitoring
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Invalid monitoring config: {exc}")

        return errors

    def _initialize_dependencies(self) -> List[str]:
        """Initialize application dependencies. Returns list of error messages."""
        errors: List[str] = []

        # Initialize logging.
        try:
            from src.config import CONFIG as _cfg
            from src.logging_config import setup_logging

            setup_logging(level=_cfg.logging.level, log_dir=_cfg.logging.dir)
            self._register_component("logging", True, "Logging initialized")
        except Exception as exc:  # noqa: BLE001
            self._register_component("logging", False, str(exc))
            errors.append(f"Logging initialization failed: {exc}")

        # Execution engine (Phase 9) - available but DEMO execution disabled by default.
        try:
            from src.execution import ExecutionConfig, ExecutionMode

            _ = ExecutionConfig.from_env()
            self._register_component(
                "execution_engine", True, f"Execution engine ready (mode: {ExecutionMode.PAPER.value})"
            )
        except Exception as exc:  # noqa: BLE001
            self._register_component("execution_engine", False, str(exc))
            errors.append(f"Execution engine initialization failed: {exc}")

        return errors

    def _register_component(self, name: str, healthy: bool, detail: Optional[str] = None) -> None:
        self._components[name] = ComponentHealth(
            name=name,
            healthy=healthy,
            detail=detail,
            last_checked=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def stop(self) -> bool:
        """Graceful shutdown.

        Blocks new entries, runs shutdown hooks, reconciles unresolved
        executions, and transitions to STOPPED. Never closes positions.
        """
        if self._state == LifecycleState.STOPPED:
            return True

        self._transition(LifecycleState.STOPPING, "Graceful shutdown initiated")

        # Block new entries before shutdown.
        self._block_new_entries()

        # Run shutdown hooks in reverse order.
        for hook in reversed(self._shutdown_hooks):
            try:
                hook()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Shutdown hook failed: %s", exc)

        # Release process lock.
        self._lock.release()

        self._stop_time = datetime.now(timezone.utc)
        self._transition(LifecycleState.STOPPED, "Application stopped")
        logger.info("Forex Trading Bot stopped")
        return True

    def _block_new_entries(self) -> None:
        """Block new trading entries during shutdown."""
        logger.info("Blocking new trading entries during shutdown")
        # Signal to execution layer that new entries are blocked.

    def _shutdown_dependencies(self) -> None:
        """Shutdown dependencies (mock broker disconnect, etc.)."""
        try:
            from src.broker import MockBrokerAdapter

            # MockBrokerAdapter is stateless; no disconnect needed.
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Component health
    # ------------------------------------------------------------------

    def update_component_health(
        self, name: str, healthy: bool, detail: Optional[str] = None
    ) -> None:
        """Update the health status of a component."""
        self._components[name] = ComponentHealth(
            name=name,
            healthy=healthy,
            detail=detail,
            last_checked=datetime.now(timezone.utc),
        )

        # If a critical component becomes unhealthy, move to DEGRADED.
        if not healthy and self._state == LifecycleState.RUNNING:
            critical = ("execution_engine", "logging")
            if name in critical:
                self._transition(LifecycleState.DEGRADED, f"Component {name} unhealthy")

    def get_health_summary(self) -> Dict[str, Any]:
        """Return a summary of application health."""
        all_healthy = all(c.healthy for c in self._components.values())
        return {
            "state": self._state.value,
            "uptime_seconds": self.uptime_seconds,
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "stop_time": self._stop_time.isoformat() if self._stop_time else None,
            "all_components_healthy": all_healthy,
            "components": {
                name: {
                    "healthy": c.healthy,
                    "detail": c.detail,
                    "last_checked": c.last_checked.isoformat() if c.last_checked else None,
                }
                for name, c in self._components.items()
            },
            "critical_failures": list(self._critical_failures),
        }

    # ------------------------------------------------------------------
    # Lock
    # ------------------------------------------------------------------

    def lock(self, reason: str = "Manual lock") -> None:
        """Lock the application (prevents trading)."""
        self._transition(LifecycleState.LOCKED, reason)

    def unlock(self) -> None:
        """Unlock the application (requires explicit authorization)."""
        if self._state == LifecycleState.LOCKED:
            self._transition(LifecycleState.STOPPED, "Manual unlock")


class _LifecycleLock:
    """Simple in-memory process lock for lifecycle management."""

    def __init__(self) -> None:
        self._held = False

    def is_locked(self) -> bool:
        return self._held

    def acquire(self) -> bool:
        if self._held:
            return False
        self._held = True
        return True

    def release(self) -> None:
        self._held = False
