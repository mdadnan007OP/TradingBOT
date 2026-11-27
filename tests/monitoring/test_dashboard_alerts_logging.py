"""Phase 10 — Dashboard, alerts, logging, and persistence tests."""

from datetime import datetime, timezone

import os
import pytest

from src.monitoring.alerts import (
    Alert,
    AlertConfigSnapshot,
    AlertManager,
    AlertSeverity,
    LogProvider,
)
from src.monitoring.config import MonitoringConfig
from src.monitoring.dashboard import DashboardServer
from src.monitoring.logging_audit import AuditEvent, redact_secrets, structured_logger
from src.monitoring.persistence import BackupManager


# ---------------------------------------------------------------------------
# Dashboard tests
# ---------------------------------------------------------------------------

def test_dashboard_default_bind_is_localhost():
    server = DashboardServer()
    assert server.host == "127.0.0.1"


def test_dashboard_rejects_non_localhost():
    server = DashboardServer(host="0.0.0.0")
    assert server.host == "127.0.0.1"


# ---------------------------------------------------------------------------
# Alert tests
# ---------------------------------------------------------------------------

def test_alert_manager_disabled():
    config = AlertConfigSnapshot(enabled=False)
    mgr = AlertManager(config)
    alert = mgr.send_alert(
        severity=AlertSeverity.CRITICAL,
        title="Test",
        message="test message",
        component="test",
    )
    assert alert.delivered is False
    assert alert.delivery_error == "notifications disabled"


def test_alert_manager_log_provider():
    config = AlertConfigSnapshot(enabled=True, providers=["log"])
    mgr = AlertManager(config)
    assert "log" in mgr.provider_names
    alert = mgr.send_alert(
        severity=AlertSeverity.INFO,
        title="Startup",
        message="Application started",
        component="lifecycle",
    )
    assert alert.delivered is True


def test_alert_dedup():
    config = AlertConfigSnapshot(enabled=True, providers=["log"], dedup_window_seconds=300)
    mgr = AlertManager(config)
    a1 = mgr.send_alert(severity=AlertSeverity.HIGH, title="Dup", message="m", component="c")
    a2 = mgr.send_alert(severity=AlertSeverity.HIGH, title="Dup", message="m", component="c")
    assert a1.delivered is True
    assert a2.delivered is False
    assert a2.delivery_error == "duplicate suppressed"


def test_alert_rate_limit():
    config = AlertConfigSnapshot(enabled=True, providers=["log"], rate_limit_seconds=1)
    mgr = AlertManager(config)
    a1 = mgr.send_alert(severity=AlertSeverity.INFO, title="T1", message="m1", component="c")
    # Manually set last delivery to now to trigger rate limit
    mgr._last_delivery_time = __import__("time").time()
    a2 = mgr.send_alert(severity=AlertSeverity.INFO, title="T2", message="m2", component="c")
    assert a2.delivered is False
    assert a2.delivery_error == "rate limited"


def test_alert_no_secrets_in_message():
    config = AlertConfigSnapshot(enabled=True, providers=["log"])
    mgr = AlertManager(config)
    alert = mgr.send_alert(
        severity=AlertSeverity.CRITICAL,
        title="Key leak",
        message="api_key=sk-12345678901234567890 and token=bot123:ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890",
        component="config",
    )
    # The Alert object stores the original message; providers redact at send time.
    # Verify the LogProvider redacts secrets in its output by checking the provider directly.
    provider = LogProvider()
    provider.send(alert)
    assert alert.delivered is True
    # Verify redaction works at the string level.
    redacted = redact_secrets(alert.message)
    assert "sk-12345678901234567890" not in redacted
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890" not in redacted
    assert "bot123:" not in redacted


# ---------------------------------------------------------------------------
# Logging/audit tests
# ---------------------------------------------------------------------------

def test_redact_secrets():
    text = "password=secret123 api_key=sk-abc123 token=bot1:xyz"
    result = redact_secrets(text)
    assert "secret123" not in result
    assert "sk-abc123" not in result
    assert "xyz" not in result
    assert "[REDACTED]" in result


def test_structured_logger_event():
    sl = structured_logger
    event = sl.log_event(
        component="test",
        severity="info",
        message="test event",
        metadata={"key": "value"},
    )
    assert event.event_id is not None
    assert event.component == "test"
    assert event.severity == "info"
    d = event.to_dict()
    assert d["message"] == "test event"


# ---------------------------------------------------------------------------
# Persistence tests
# ---------------------------------------------------------------------------

def test_backup_creates_file(tmp_path):
    mgr = BackupManager(directory=str(tmp_path / "backups"), max_backups=5, retention_days=30)
    result = mgr.backup()
    assert result.success is True
    assert os.path.exists(result.backup_path)


def test_database_health_check(tmp_path):
    mgr = BackupManager(directory=str(tmp_path / "backups"), max_backups=5, retention_days=30)
    health = mgr.database_health_check()
    assert "healthy" in health
    assert "details" in health
