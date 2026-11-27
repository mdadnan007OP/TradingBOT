# Backup and Recovery — Forex Trading Bot (Phase 10)

This document describes the backup, restore, and recovery procedures for the
Automated Forex Trading Bot.

---

## Backup Overview

The backup system creates durable, timestamped ZIP archives of trading data.
Backups are stored locally in the `backups/` directory.

### What's Backed Up

| Data | Source | Included by Default |
|------|--------|---------------------|
| Execution journal | `.execution_journal/journal.jsonl` | Yes |
| Risk breakers | `.emergency_stop/breakers.json` | Yes |
| Config template | `.env.example` | Yes |
| Application logs | `logs/` | Yes |

### What's NEVER Backed Up (Security)

- `.env` — contains secrets, never backed up
- `secrets.json` — never backed up
- `credentials.json` — never backed up
- SSH keys (`id_rsa`, `id_ed25519`) — never backed up
- Any file matching sensitive patterns — excluded

---

## Backup Operations

### Create a Backup

```powershell
.\scripts\backup.ps1
```

This creates `backups/backup-YYYYMMDD-HHMMSS.zip` with:
- Execution journal entries
- Risk/emergency stop state
- Configuration template
- Log files
- A `manifest.json` with backup metadata

### List Available Backups

```powershell
.\scripts\restore.ps1 -List
```

### Verify Backup Integrity

```powershell
# The backup script verifies integrity during creation.
# To verify an existing backup manually:
.\scripts\restore.ps1 -BackupId backup-20261126-120000
# (without -Confirm, this just lists and verifies)
```

### Restore from Backup

```powershell
.\scripts\restore.ps1 -BackupId backup-20261126-120000 -Confirm
```

**Warning:** Restore overwrites existing files. The `-Confirm` flag is required.
This does **not** delete existing trading history automatically.

---

## Retention Policy

| Setting | Default | Description |
|---------|---------|-------------|
| Max backups | 10 | Maximum number of backup files retained |
| Retention days | 30 | Maximum age of backups in days |

When the maximum is exceeded, oldest backups are deleted first.
When a backup exceeds the retention age, it is deleted.

These values are configurable via environment variables:
- `MONITORING_MAX_BACKUPS`
- `MONITORING_BACKUP_RETENTION_DAYS`

---

## Recovery Procedures

### After Application Crash

1. Check logs: `logs/trading_bot.log` and `logs/audit_errors.log`
2. Start the bot: `.\scripts\start.ps1`
3. The recovery manager automatically:
   - Loads the persistent execution journal
   - Identifies unresolved submissions
   - Reconciles with broker orders, positions, and deals
   - Preserves UNKNOWN execution states
   - Never automatically resends uncertain orders
4. Review unresolved executions before resuming trading.

### After MT5 Disconnection

1. Verify MT5 terminal is running and connected.
2. Verify the demo account is still logged in.
3. Run `.\scripts\health_check.ps1`.
4. If the watchdog blocked execution, verify the connection is restored.
5. Restart with `.\scripts\restart.ps1` if needed.

### After Server Reboot

1. Verify MT5 terminal is running and logged into the demo account.
2. Verify external Python API trading permission is enabled.
3. Start the bot: `.\scripts\start.ps1`
4. Check that pre-reboot unresolved executions are reconciled.
5. Verify health status is `RUNNING` or `DEGRADED`.

### Recovering Unresolved Executions

1. Check the execution journal for non-terminal states:
   - `.execution_journal/journal.jsonl`
2. Look for: SUBMITTED, ACCEPTED, PARTIALLY_FILLED, UNKNOWN
3. **Never automatically resend an uncertain order.**
4. Reconcile with broker orders, positions, and deals.
5. Require explicit recovery authorization when ambiguity remains.
6. Once resolved, mark the execution as RECONCILED.

---

## Data Integrity

### Backup Integrity Verification

Each backup ZIP contains a `manifest.json` with:
- Backup ID
- Timestamp
- Files included
- Version

Integrity can be verified by:
1. Opening the ZIP and checking all files extract correctly
2. Verifying the manifest is present and valid
3. Checking file counts match the manifest

### Never Delete Trading History

- Backup operations never delete existing trading history.
- Restore operations overwrite files but do not delete journal entries.
- The retention policy only removes old backup ZIP files, not live data.

---

## Recovery Safety Rules

1. **Never automatically resend an uncertain order.**
2. **Preserve UNKNOWN execution states until resolved.**
3. **Require explicit recovery authorization when ambiguity remains.**
4. **Recovery never removes persistent emergency stops or risk lockouts.**
5. **If Risk Engine, Account Identity, or Reconciliation is unavailable, block new demo execution.**

---

## Backup and Restore Test

A documented backup and restore test should be performed periodically:

1. Create a backup: `.\scripts\backup.ps1`
2. Verify integrity: `.\scripts\restore.ps1 -BackupId <id>` (without -Confirm)
3. Simulate data loss (move/copy journal to temp location)
4. Restore from backup: `.\scripts\restore.ps1 -BackupId <id> -Confirm`
5. Verify the journal contains the expected entries
6. Start the bot and confirm it reads the restored journal

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Backup fails | Check disk space, permissions, and that `backups/` directory exists |
| Restore fails | Verify backup ZIP is not corrupted, `-Confirm` flag is provided |
| Journal not found | Check `.execution_journal/` directory exists |
| Integrity check fails | The backup ZIP may be corrupted; create a new backup |
| Secrets in backup | `.env` is always excluded; verify no secret files were manually added |
