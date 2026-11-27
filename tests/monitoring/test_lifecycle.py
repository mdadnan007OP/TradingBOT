"""Phase 10 — Lifecycle manager tests."""

import os
from datetime import datetime, timezone

import pytest

from src.monitoring.lifecycle import ApplicationLifecycleManager, LifecycleState


def test_initial_state_is_initializing():
    mgr = ApplicationLifecycleManager()
    assert mgr.state == LifecycleState.INITIALIZING
    assert not mgr.is_running


def test_start_transitions_to_running():
    mgr = ApplicationLifecycleManager()
    assert mgr.start() is True
    assert mgr.state in (LifecycleState.RUNNING, LifecycleState.DEGRADED)
    assert mgr.is_running or mgr.state == LifecycleState.DEGRADED


def test_stop_transitions_to_stopped():
    mgr = ApplicationLifecycleManager()
    mgr.start()
    assert mgr.stop() is True
    assert mgr.state == LifecycleState.STOPPED


def test_transition_history_recorded():
    mgr = ApplicationLifecycleManager()
    mgr.start()
    mgr.stop()
    history = mgr.transition_history
    assert len(history) >= 2
    states = [t.to_state for t in history]
    assert LifecycleState.STOPPED in states


def test_component_health_update():
    mgr = ApplicationLifecycleManager()
    mgr.update_component_health("test_component", True, "OK")
    health = mgr.component_health
    assert "test_component" in health
    assert health["test_component"].healthy is True


def test_health_summary():
    mgr = ApplicationLifecycleManager()
    mgr.start()
    summary = mgr.get_health_summary()
    assert "state" in summary
    assert "components" in summary
    assert "uptime_seconds" in summary


def test_lock_and_unlock():
    mgr = ApplicationLifecycleManager()
    mgr.lock("manual lock")
    assert mgr.is_locked
    mgr.unlock()
    assert mgr.state == LifecycleState.STOPPED


def test_lifecycle_states_enum():
    assert LifecycleState.INITIALIZING.value == "INITIALIZING"
    assert LifecycleState.STARTING.value == "STARTING"
    assert LifecycleState.RUNNING.value == "RUNNING"
    assert LifecycleState.DEGRADED.value == "DEGRADED"
    assert LifecycleState.STOPPING.value == "STOPPING"
    assert LifecycleState.STOPPED.value == "STOPPED"
    assert LifecycleState.FAILED.value == "FAILED"
    assert LifecycleState.LOCKED.value == "LOCKED"
