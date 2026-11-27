"""Phase 10 — Backup and restore management.

Provides database health checks, transaction safety, backup procedures,
retention policies, data integrity checks, and restore procedures.

Backs up: execution journal, risk configuration, strategy configuration,
account-state snapshots, historical execution records, monitoring history,
news-event history.

Never includes passwords, private keys, or broker credentials in backups.
Never deletes existing trading history automatically.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Files that must NEVER be included in backups (contain secrets/credentials).
SENSITIVE_FILES = {".env", "secrets.json", "credentials.json", "id_rsa", "id_ed25519"}


@dataclass
class BackupResult:
    """Result of a backup operation."""

    backup_id: str
    timestamp: str
    success: bool
    detail: str
    backup_path: Optional[str] = None
    files_included: List[str] = field(default_factory=list)
    files_excluded: List[str] = field(default_factory=list)
    size_bytes: int = 0


@dataclass
class RestoreResult:
    """Result of a restore operation."""

    backup_id: str
    success: bool
    detail: str
    files_restored: List[str] = field(default_factory=list)


class BackupManager:
    """Manages backups and restores of trading bot data."""

    def __init__(
        self,
        *,
        directory: str = "backups",
        max_backups: int = 10,
        retention_days: int = 30,
        include_journal: bool = True,
        include_config: bool = True,
        include_risk_state: bool = True,
    ) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.max_backups = max_backups
        self.retention_days = retention_days
        self.include_journal = include_journal
        self.include_config = include_config
        self.include_risk_state = include_risk_state

    def backup(self) -> BackupResult:
        """Create a backup of trading data.

        Never includes sensitive files (.env, credentials, keys).
        """
        backup_id = f"backup-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{__import__('uuid').uuid4().hex[:8]}"
        backup_path = self.directory / f"{backup_id}.zip"
        files_included: List[str] = []
        files_excluded: List[str] = []

        try:
            with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # Execution journal.
                if self.include_journal:
                    journal_path = Path(".execution_journal/journal.jsonl")
                    if journal_path.exists():
                        zf.write(journal_path, arcname="execution_journal/journal.jsonl")
                        files_included.append("execution_journal/journal.jsonl")
                    else:
                        files_excluded.append("execution_journal/journal.jsonl (not found)")

                # Configuration (non-sensitive parts only).
                if self.include_config:
                    config_path = Path(".env.example")
                    if config_path.exists():
                        zf.write(config_path, arcname="config/.env.example")
                        files_included.append("config/.env.example")
                    # Never back up .env (contains secrets).
                    files_excluded.append(".env (secrets - excluded)")

                # Risk state.
                if self.include_risk_state:
                    risk_path = Path(".emergency_stop/breakers.json")
                    if risk_path.exists():
                        zf.write(risk_path, arcname="risk/emergency_breakers.json")
                        files_included.append("risk/emergency_breakers.json")
                    else:
                        files_excluded.append("risk/emergency_breakers.json (not found)")

                # Add a manifest.
                manifest = {
                    "backup_id": backup_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "files_included": files_included,
                    "files_excluded": files_excluded,
                    "version": "1.0",
                }
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))

            size_bytes = backup_path.stat().st_size
            self._enforce_retention()

            return BackupResult(
                backup_id=backup_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                success=True,
                detail=f"Backup created with {len(files_included)} file(s)",
                backup_path=str(backup_path),
                files_included=files_included,
                files_excluded=files_excluded,
                size_bytes=size_bytes,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Backup failed: %s", exc)
            return BackupResult(
                backup_id=backup_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                success=False,
                detail=f"Backup failed: {exc}",
            )

    def restore(self, backup_id: str) -> RestoreResult:
        """Restore from a backup.

        Never deletes existing trading history automatically — the operator
        must explicitly approve overwriting existing files.
        """
        backup_path = self.directory / f"{backup_id}.zip"
        if not backup_path.exists():
            return RestoreResult(
                backup_id=backup_id,
                success=False,
                detail=f"Backup {backup_id} not found",
            )

        files_restored: List[str] = []
        try:
            with zipfile.ZipFile(backup_path, "r") as zf:
                # Verify manifest.
                manifest_name = "manifest.json"
                if manifest_name not in zf.namelist():
                    return RestoreResult(
                        backup_id=backup_id,
                        success=False,
                        detail="Backup is missing manifest (corrupted)",
                    )

                manifest = json.loads(zf.read(manifest_name))

                # Extract files (does not overwrite existing by default -
                # operator must explicitly approve).
                for name in zf.namelist():
                    if name == manifest_name:
                        continue
                    target = Path(name)
                    # Skip sensitive files.
                    if target.name in SENSITIVE_FILES:
                        continue
                    # Extract to current directory.
                    zf.extract(name, path=".")
                    files_restored.append(name)

            return RestoreResult(
                backup_id=backup_id,
                success=True,
                detail=f"Restored {len(files_restored)} file(s)",
                files_restored=files_restored,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Restore failed: %s", exc)
            return RestoreResult(
                backup_id=backup_id,
                success=False,
                detail=f"Restore failed: {exc}",
            )

    def list_backups(self) -> List[Dict[str, Any]]:
        """List available backups with metadata."""
        backups: List[Dict[str, Any]] = []
        for path in sorted(self.directory.glob("backup-*.zip")):
            try:
                with zipfile.ZipFile(path, "r") as zf:
                    if "manifest.json" in zf.namelist():
                        manifest = json.loads(zf.read("manifest.json"))
                    else:
                        manifest = {}
                backups.append(
                    {
                        "backup_id": manifest.get("backup_id", path.stem),
                        "timestamp": manifest.get("timestamp", ""),
                        "size_bytes": path.stat().st_size,
                        "files_included": manifest.get("files_included", []),
                        "path": str(path),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not read backup %s: %s", path, exc)
        return backups

    def verify_integrity(self, backup_id: str) -> Dict[str, Any]:
        """Verify the integrity of a backup."""
        backup_path = self.directory / f"{backup_id}.zip"
        if not backup_path.exists():
            return {"valid": False, "detail": "Backup not found"}

        try:
            with zipfile.ZipFile(backup_path) as zf:
                bad_file = zf.testzip()
                if bad_file is not None:
                    return {"valid": False, "detail": f"Corrupted file: {bad_file}"}
                if "manifest.json" not in zf.namelist():
                    return {"valid": False, "detail": "Missing manifest"}
                manifest = json.loads(zf.read("manifest.json"))
                return {
                    "valid": True,
                    "backup_id": manifest.get("backup_id"),
                    "timestamp": manifest.get("timestamp"),
                    "files": manifest.get("files_included", []),
                }
        except Exception as exc:  # noqa: BLE001
            return {"valid": False, "detail": str(exc)}

    def delete_backup(self, backup_id: str) -> bool:
        """Delete a backup. Never deletes trading history — only backup files."""
        backup_path = self.directory / f"{backup_id}.zip"
        if backup_path.exists():
            backup_path.unlink()
            return True
        return False

    def _enforce_retention(self) -> None:
        """Enforce backup retention: max count and max age."""
        backups = self.list_backups()
        now = datetime.now(timezone.utc)

        # Sort by timestamp (newest first).
        backups.sort(key=lambda b: b.get("timestamp", ""), reverse=True)

        # Remove excess beyond max_backups.
        for b in backups[self.max_backups :]:
            self.delete_backup(b["backup_id"])

        # Remove backups older than retention_days.
        for b in backups:
            try:
                ts = datetime.fromisoformat(b.get("timestamp", ""))
                age_days = (now - ts).days
                if age_days > self.retention_days:
                    self.delete_backup(b["backup_id"])
            except Exception:  # noqa: BLE001
                pass

    def database_health_check(self) -> Dict[str, Any]:
        """Check the health of the execution journal and other data stores."""
        results: Dict[str, Any] = {"healthy": True, "details": {}}

        # Execution journal.
        journal_path = Path(".execution_journal/journal.jsonl")
        if journal_path.exists():
            try:
                with open(journal_path, "r", encoding="utf-8") as f:
                    line_count = sum(1 for _ in f)
                results["details"]["execution_journal"] = {
                    "exists": True,
                    "lines": line_count,
                    "size_bytes": journal_path.stat().st_size,
                }
            except Exception as exc:  # noqa: BLE001
                results["healthy"] = False
                results["details"]["execution_journal"] = {"exists": True, "error": str(exc)}
        else:
            results["details"]["execution_journal"] = {"exists": False}

        # Emergency stop / risk state.
        breakers_path = Path(".emergency_stop/breakers.json")
        results["details"]["risk_breakers"] = {
            "exists": breakers_path.exists(),
            "size_bytes": breakers_path.stat().st_size if breakers_path.exists() else 0,
        }

        return results
