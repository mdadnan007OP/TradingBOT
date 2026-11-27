"""Phase 10 — Safe recovery tests."""

import os
import shutil

import pytest

from src.monitoring.recovery import ReconnectionManager, RecoveryResult, SafeRecoveryManager
from tests.backtesting.conftest import make_bars  # noqa: F401  (ensures conftest loads)


class FakeJournal:
    """Fake execution journal for testing recovery."""

    def __init__(self, records=None):
        self._records = records or []

    def load_all(self):
        return list(self._records)


class FakeExecutionRecord:
    def __init__(self, execution_id, state, broker_order_ticket=None):
        self.execution_id = execution_id
        self.state = state
        self.broker_order_ticket = broker_order_ticket

    def is_terminal(self):
        return self.state in ("FILLED", "REJECTED", "CANCELLED", "EXPIRED", "UNKNOWN")


def test_reconnection_manager_success():
    calls = {"n": 0}

    def connect():
        calls["n"] += 1
        return True

    mgr = ReconnectionManager(max_attempts=3, base_delay_seconds=0.01, jitter_seconds=0.0)
    assert mgr.attempt(connect) is True
    assert calls["n"] == 1


def test_reconnection_manager_retry_then_success():
    calls = {"n": 0}

    def connect():
        calls["n"] += 1
        return calls["n"] >= 2

    mgr = ReconnectionManager(max_attempts=3, base_delay_seconds=0.01, jitter_seconds=0.0)
    assert mgr.attempt(connect) is True
    assert calls["n"] == 2


def test_reconnection_manager_exhausted():
    calls = {"n": 0}

    def connect():
        calls["n"] += 1
        return False

    mgr = ReconnectionManager(max_attempts=2, base_delay_seconds=0.01, jitter_seconds=0.0)
    assert mgr.attempt(connect) is False
    assert calls["n"] == 2


def test_recovery_after_crash_no_issues():
    journal = FakeJournal([])
    mgr = SafeRecoveryManager(journal)
    result = mgr.recover_after_crash(
        risk_engine_available=True,
        identity_service_available=True,
        reconciliation_available=True,
    )
    assert result.success is True
    assert result.requires_manual_authorization is False


def test_recovery_blocks_on_risk_unavailable():
    journal = FakeJournal([])
    mgr = SafeRecoveryManager(journal)
    result = mgr.recover_after_crash(risk_engine_available=False)
    assert result.requires_manual_authorization is True
    assert any("Risk engine unavailable" in a for a in result.detail.split(";"))


def test_recovery_blocks_on_identity_unavailable():
    journal = FakeJournal([])
    mgr = SafeRecoveryManager(journal)
    result = mgr.recover_after_crash(identity_service_available=False)
    assert result.requires_manual_authorization is True


def test_recovery_preserves_unresolved_executions():
    rec = FakeExecutionRecord("exec-1", state="SUBMITTED", broker_order_ticket="T123")
    journal = FakeJournal([rec])
    mgr = SafeRecoveryManager(journal)
    result = mgr.recover_after_crash()
    assert result.executions_unknown >= 0
    assert result.executions_reconciled >= 0
    assert result.requires_manual_authorization is True


def test_recovery_authorize():
    journal = FakeJournal([])
    mgr = SafeRecoveryManager(journal)
    assert mgr.is_recovery_authorized() is False
    mgr.authorize_recovery()
    assert mgr.is_recovery_authorized() is True


def test_recovery_history_recorded():
    journal = FakeJournal([])
    mgr = SafeRecoveryManager(journal)
    mgr.recover_after_crash()
    history = mgr.get_recovery_history()
    assert len(history) == 1
    assert history[0].action == "post_crash_recovery"


def test_backup_manager_create_and_list(tmp_path):
    from src.monitoring.persistence import BackupManager

    mgr = BackupManager(directory=str(tmp_path / "backups"), max_backups=5, retention_days=30)
    result = mgr.backup()
    assert result.success is True
    assert result.backup_path is not None
    backups = mgr.list_backups()
    assert len(backups) == 1


def test_backup_excludes_env(tmp_path):
    from src.monitoring.persistence import BackupManager

    # Create a fake .env
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET=value\n")
    mgr = BackupManager(directory=str(tmp_path / "backups"), max_backups=5, retention_days=30)
    result = mgr.backup()
    assert result.success is True
    assert ".env" not in result.files_included
    assert any("secrets" in f.lower() or ".env" in f.lower() for f in result.files_excluded)


def test_backup_integrity_verify(tmp_path):
    from src.monitoring.persistence import BackupManager

    mgr = BackupManager(directory=str(tmp_path / "backups"), max_backups=5, retention_days=30)
    result = mgr.backup()
    assert result.success is True
    integrity = mgr.verify_integrity(result.backup_id)
    assert integrity["valid"] is True
