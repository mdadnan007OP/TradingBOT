"""Phase 10 — Monitoring, alerting, reliability, and deployment preparation.

Modules:
- config: Monitoring configuration (dashboard, alerts, watchdog, backup)
- lifecycle: ApplicationLifecycleManager with explicit lifecycle states
- health: Centralized system health monitoring
- heartbeat: Heartbeat registry and watchdog
- recovery: Safe recovery mechanisms (journal reconciliation, reconnection)
- dashboard: Read-only localhost-only HTTP dashboard
- alerts: Notification and alert system (email, Telegram, webhook, log)
- logging_audit: Structured logging and audit trails
- persistence: Backup and restore management
"""

from src.monitoring.alerts import Alert, AlertManager, AlertSeverity
from src.monitoring.config import MonitoringConfig, MonitoringConfigError
from src.monitoring.dashboard import DashboardHandler, DashboardServer
from src.monitoring.health import (
    HealthChecker,
    HealthService,
    HealthStatus,
    SubsystemHealth,
    create_default_health_service,
)
from src.monitoring.heartbeat import (
    HeartbeatRecord,
    HeartbeatRegistry,
    HeartbeatStatus,
    HeartbeatReporter,
    Watchdog,
)
from src.monitoring.logging_audit import AuditEvent, StructuredLogger, redact_secrets, structured_logger
from src.monitoring.lifecycle import ApplicationLifecycleManager, LifecycleState, LifecycleTransition
from src.monitoring.persistence import BackupManager, BackupResult, RestoreResult
from src.monitoring.recovery import RecoveryResult, ReconnectionManager, SafeRecoveryManager

__all__ = [
    "Alert",
    "AlertManager",
    "AlertSeverity",
    "AuditEvent",
    "BackupManager",
    "BackupResult",
    "DashboardHandler",
    "DashboardServer",
    "HealthChecker",
    "HealthService",
    "HealthStatus",
    "LifecycleState",
    "LifecycleTransition",
    "MonitoringConfig",
    "MonitoringConfigError",
    "RestoreResult",
    "RecoveryResult",
    "ReconnectionManager",
    "SafeRecoveryManager",
    "StructuredLogger",
    "SubsystemHealth",
    "Watchdog",
    "HeartbeatRecord",
    "HeartbeatRegistry",
    "HeartbeatStatus",
    "HeartbeatReporter",
    "ApplicationLifecycleManager",
    "create_default_health_service",
    "redact_secrets",
    "structured_logger",
]
