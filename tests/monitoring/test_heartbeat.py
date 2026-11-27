"""Phase 10 — Heartbeat and watchdog tests."""

from datetime import datetime, timedelta, timezone

import pytest

from src.monitoring.heartbeat import (
    HeartbeatRecord,
    HeartbeatRegistry,
    HeartbeatReporter,
    HeartbeatStatus,
    Watchdog,
)


def test_heartbeat_registry_record_and_get():
    registry = HeartbeatRegistry()
    registry.update(
        name="broker",
        status=HeartbeatStatus.ALIVE,
        last_successful_operation=datetime.now(timezone.utc),
        last_heartbeat_time=datetime.now(timezone.utc),
        processing_latency_ms=5.0,
        last_error=None,
        failure_count=0,
    )
    record = registry.get("broker")
    assert record is not None
    assert record.status == HeartbeatStatus.ALIVE


def test_heartbeat_stale_detection():
    registry = HeartbeatRegistry()
    old_time = datetime.now(timezone.utc) - timedelta(seconds=60)
    registry.update(
        name="market_data",
        status=HeartbeatStatus.ALIVE,
        last_successful_operation=None,
        last_heartbeat_time=old_time,
        processing_latency_ms=None,
        last_error=None,
        failure_count=0,
    )
    assert registry.get("market_data").is_stale(30.0) is True
    assert registry.get("market_data").is_stale(120.0) is False


def test_stale_subsystems():
    registry = HeartbeatRegistry()
    old_time = datetime.now(timezone.utc) - timedelta(seconds=60)
    registry.update(
        name="slow_sub",
        status=HeartbeatStatus.ALIVE,
        last_successful_operation=None,
        last_heartbeat_time=old_time,
        processing_latency_ms=None,
        last_error=None,
        failure_count=0,
    )
    stale = registry.stale_subsystems(30.0)
    assert "slow_sub" in stale


def test_heartbeat_reporter_success():
    registry = HeartbeatRegistry()
    reporter = HeartbeatReporter("test_sub", registry)
    reporter.success(processing_latency_ms=10.0)
    record = registry.get("test_sub")
    assert record is not None
    assert record.status == HeartbeatStatus.ALIVE
    assert record.failure_count == 0
    assert record.processing_latency_ms == 10.0


def test_heartbeat_reporter_failure():
    registry = HeartbeatRegistry()
    reporter = HeartbeatReporter("test_sub", registry)
    reporter.failure("connection lost", processing_latency_ms=100.0)
    record = registry.get("test_sub")
    assert record.status == HeartbeatStatus.DEAD
    assert record.last_error == "connection lost"
    assert record.failure_count == 1


def test_watchdog_no_issues():
    registry = HeartbeatRegistry()
    now = datetime.now(timezone.utc)
    # Register all required subsystems as healthy.
    for name in ("broker", "risk_engine", "account_identity", "reconciliation"):
        registry.update(
            name=name,
            status=HeartbeatStatus.ALIVE,
            last_successful_operation=now,
            last_heartbeat_time=now,
            processing_latency_ms=5.0,
            last_error=None,
            failure_count=0,
        )
    watchdog = Watchdog(registry)
    result = watchdog.check()
    assert result["block_execution"] is False
    assert result["issues"] == []


def test_watchdog_blocks_on_stale_heartbeat():
    registry = HeartbeatRegistry()
    old_time = datetime.now(timezone.utc) - timedelta(seconds=60)
    registry.update(
        name="risk_engine",
        status=HeartbeatStatus.ALIVE,
        last_successful_operation=None,
        last_heartbeat_time=old_time,
        processing_latency_ms=None,
        last_error=None,
        failure_count=0,
    )
    watchdog = Watchdog(registry, heartbeat_timeout_seconds=30.0)
    result = watchdog.check()
    assert result["block_execution"] is True
    assert any("Heartbeat stale" in i for i in result["issues"])


def test_watchdog_blocks_on_risk_engine_dead():
    registry = HeartbeatRegistry()
    registry.update(
        name="risk_engine",
        status=HeartbeatStatus.DEAD,
        last_successful_operation=None,
        last_heartbeat_time=datetime.now(timezone.utc) - timedelta(seconds=5),
        processing_latency_ms=None,
        last_error="unavailable",
        failure_count=3,
    )
    watchdog = Watchdog(registry)
    result = watchdog.check()
    assert result["block_execution"] is True
    assert any("Risk engine unavailable" in i for i in result["issues"])
