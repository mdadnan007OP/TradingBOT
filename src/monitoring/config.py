"""Phase 10 monitoring, alerting and dashboard configuration.

All values are loaded from environment variables with safe defaults. The
dashboard is localhost-only and read-only by default. All notification
providers are optional and disabled unless explicitly configured.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, str(default)).strip().lower()
    return raw in ("true", "1", "yes", "on")


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _get_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _get_list(name: str, default: List[str] | None = None) -> List[str]:
    if default is None:
        default = []
    raw = os.environ.get(name, "")
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class DashboardConfig:
    """Read-only monitoring dashboard configuration."""

    enabled: bool = False
    bind_host: str = "127.0.0.1"
    port: int = 8765
    read_only: bool = True
    require_auth: bool = False
    auth_token: str = ""
    max_history_items: int = 200

    def __post_init__(self) -> None:
        if self.bind_host not in ("127.0.0.1", "localhost", "::1"):
            object.__setattr__(self, "bind_host", "127.0.0.1")
        if not (1024 <= self.port <= 65535):
            object.__setattr__(self, "port", 8765)


@dataclass(frozen=True)
class AlertConfig:
    """Notification alert configuration. All providers optional/disabled."""

    enabled: bool = False
    providers: List[str] = field(default_factory=list)
    rate_limit_seconds: int = 60
    dedup_window_seconds: int = 300
    max_history_items: int = 1000

    # Email (optional)
    email_smtp_host: str = ""
    email_smtp_port: int = 587
    email_smtp_user: str = ""
    email_smtp_password: str = ""
    email_from: str = ""
    email_to: List[str] = field(default_factory=list)
    email_use_tls: bool = True

    # Telegram Bot API (optional)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Generic webhook (optional)
    webhook_url: str = ""
    webhook_secret: str = ""

    def __post_init__(self) -> None:
        if self.rate_limit_seconds < 1:
            object.__setattr__(self, "rate_limit_seconds", 1)
        if self.dedup_window_seconds < 1:
            object.__setattr__(self, "dedup_window_seconds", 1)


@dataclass(frozen=True)
class WatchdogConfig:
    """Watchdog and recovery configuration."""

    enabled: bool = True
    heartbeat_timeout_seconds: int = 30
    market_data_stale_seconds: int = 60
    mt5_disconnect_timeout_seconds: int = 30
    max_reconnect_attempts: int = 5
    reconnect_base_delay_seconds: float = 2.0
    reconnect_jitter_seconds: float = 1.0
    block_execution_on_unavailable_risk: bool = True
    block_execution_on_unavailable_identity: bool = True
    block_execution_on_unavailable_reconciliation: bool = True

    def __post_init__(self) -> None:
        if self.heartbeat_timeout_seconds < 5:
            object.__setattr__(self, "heartbeat_timeout_seconds", 5)
        if self.max_reconnect_attempts < 0:
            object.__setattr__(self, "max_reconnect_attempts", 0)


@dataclass(frozen=True)
class BackupConfig:
    """Backup and restore configuration."""

    enabled: bool = True
    directory: str = "backups"
    max_backups: int = 10
    include_journal: bool = True
    include_config: bool = True
    include_risk_state: bool = True
    retention_days: int = 30

    def __post_init__(self) -> None:
        if self.max_backups < 1:
            object.__setattr__(self, "max_backups", 1)
        if self.retention_days < 1:
            object.__setattr__(self, "retention_days", 1)


@dataclass(frozen=True)
class MonitoringConfig:
    """Top-level monitoring configuration."""

    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    watchdog: WatchdogConfig = field(default_factory=WatchdogConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    log_retention_days: int = 30
    max_log_file_mb: int = 5
    health_check_interval_seconds: int = 10
    heartbeat_interval_seconds: int = 5
    structured_logging: bool = True
    redact_secrets: bool = True

    def __post_init__(self) -> None:
        if self.health_check_interval_seconds < 1:
            object.__setattr__(self, "health_check_interval_seconds", 1)
        if self.heartbeat_interval_seconds < 1:
            object.__setattr__(self, "heartbeat_interval_seconds", 1)
        if self.log_retention_days < 1:
            object.__setattr__(self, "log_retention_days", 1)
        if self.max_log_file_mb < 1:
            object.__setattr__(self, "max_log_file_mb", 1)

    @classmethod
    def from_env(cls) -> "MonitoringConfig":
        """Build MonitoringConfig from environment variables (fail-closed)."""
        return cls(
            dashboard=DashboardConfig(
            enabled=_get_bool("MONITORING_DASHBOARD_ENABLED", False),
            bind_host=_get_str("MONITORING_DASHBOARD_HOST", "127.0.0.1"),
            port=_get_int("MONITORING_DASHBOARD_PORT", 8765),
            read_only=_get_bool("MONITORING_DASHBOARD_READ_ONLY", True),
            require_auth=_get_bool("MONITORING_DASHBOARD_REQUIRE_AUTH", False),
            auth_token=_get_str("MONITORING_DASHBOARD_AUTH_TOKEN", ""),
            max_history_items=_get_int("MONITORING_DASHBOARD_MAX_HISTORY", 200),
        ),
        alerts=AlertConfig(
            enabled=_get_bool("MONITORING_ALERTS_ENABLED", False),
            providers=_get_list("MONITORING_ALERT_PROVIDERS", []),
            rate_limit_seconds=_get_int("MONITORING_ALERT_RATE_LIMIT_SECONDS", 60),
            dedup_window_seconds=_get_int("MONITORING_ALERT_DEDUP_WINDOW_SECONDS", 300),
            max_history_items=_get_int("MONITORING_ALERT_MAX_HISTORY", 1000),
            email_smtp_host=_get_str("MONITORING_EMAIL_SMTP_HOST", ""),
            email_smtp_port=_get_int("MONITORING_EMAIL_SMTP_PORT", 587),
            email_smtp_user=_get_str("MONITORING_EMAIL_SMTP_USER", ""),
            email_smtp_password=_get_str("MONITORING_EMAIL_SMTP_PASSWORD", ""),
            email_from=_get_str("MONITORING_EMAIL_FROM", ""),
            email_to=_get_list("MONITORING_EMAIL_TO", []),
            email_use_tls=_get_bool("MONITORING_EMAIL_USE_TLS", True),
            telegram_bot_token=_get_str("MONITORING_TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=_get_str("MONITORING_TELEGRAM_CHAT_ID", ""),
            webhook_url=_get_str("MONITORING_WEBHOOK_URL", ""),
            webhook_secret=_get_str("MONITORING_WEBHOOK_SECRET", ""),
        ),
        watchdog=WatchdogConfig(
            enabled=_get_bool("MONITORING_WATCHDOG_ENABLED", True),
            heartbeat_timeout_seconds=_get_int("MONITORING_HEARTBEAT_TIMEOUT_SECONDS", 30),
            market_data_stale_seconds=_get_int("MONITORING_MARKET_DATA_STALE_SECONDS", 60),
            mt5_disconnect_timeout_seconds=_get_int(
                "MONITORING_MT5_DISCONNECT_TIMEOUT_SECONDS", 30
            ),
            max_reconnect_attempts=_get_int("MONITORING_MAX_RECONNECT_ATTEMPTS", 5),
            reconnect_base_delay_seconds=_get_float(
                "MONITORING_RECONNECT_BASE_DELAY_SECONDS", 2.0
            ),
            reconnect_jitter_seconds=_get_float(
                "MONITORING_RECONNECT_JITTER_SECONDS", 1.0
            ),
            block_execution_on_unavailable_risk=_get_bool(
                "MONITORING_BLOCK_ON_RISK_UNAVAILABLE", True
            ),
            block_execution_on_unavailable_identity=_get_bool(
                "MONITORING_BLOCK_ON_IDENTITY_UNAVAILABLE", True
            ),
            block_execution_on_unavailable_reconciliation=_get_bool(
                "MONITORING_BLOCK_ON_RECONCILIATION_UNAVAILABLE", True
            ),
        ),
        backup=BackupConfig(
            enabled=_get_bool("MONITORING_BACKUP_ENABLED", True),
            directory=_get_str("MONITORING_BACKUP_DIRECTORY", "backups"),
            max_backups=_get_int("MONITORING_MAX_BACKUPS", 10),
            include_journal=_get_bool("MONITORING_BACKUP_INCLUDE_JOURNAL", True),
            include_config=_get_bool("MONITORING_BACKUP_INCLUDE_CONFIG", True),
            include_risk_state=_get_bool("MONITORING_BACKUP_INCLUDE_RISK_STATE", True),
            retention_days=_get_int("MONITORING_BACKUP_RETENTION_DAYS", 30),
        ),
        log_retention_days=_get_int("MONITORING_LOG_RETENTION_DAYS", 30),
        max_log_file_mb=_get_int("MONITORING_MAX_LOG_FILE_MB", 5),
        health_check_interval_seconds=_get_int(
            "MONITORING_HEALTH_CHECK_INTERVAL_SECONDS", 10
        ),
        heartbeat_interval_seconds=_get_int(
            "MONITORING_HEARTBEAT_INTERVAL_SECONDS", 5
        ),
        structured_logging=_get_bool("MONITORING_STRUCTURED_LOGGING", True),
        redact_secrets=_get_bool("MONITORING_REDACT_SECRETS", True),
    )


class MonitoringConfigError(ValueError):
    """Raised when monitoring configuration is invalid."""
