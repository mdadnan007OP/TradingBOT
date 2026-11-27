# Operations Runbook — Forex Trading Bot (Phase 10)

This document provides operational procedures for running, monitoring, and
recovering the Automated Forex Trading Bot.

**Important:** Never recommend blindly restarting an application with unresolved
executions. Always verify the execution journal first.

---

## Normal Application Startup

1. Verify `.env` exists with safe defaults:
   - `EXECUTION_MODE=PAPER`
   - `DEMO_EXECUTION_ENABLED=false`
   - `DEMO_AUTOMATIC_ENABLED=false`
2. Ensure MT5 terminal is running (if DEMO mode) and logged into the demo account.
3. Verify external Python API trading permission is enabled in MT5 (Tools → Options → Expert Advisors).
4. Run: `.\scripts\start.ps1`
5. Verify the application reaches `RUNNING` or `DEGRADED` state.
6. Check the health dashboard at `http://127.0.0.1:8765/api/health` (if enabled).
7. Verify no critical failures in the health summary.

## Normal Application Shutdown

1. Run: `.\scripts\stop.ps1`
2. The script signals graceful shutdown, blocks new entries, and waits for process exit.
3. Verify the process has exited.
4. **Note:** Shutdown never closes or liquidates positions.
5. **Note:** Unresolved executions are preserved for reconciliation on next start.

## MT5 Disconnection

1. Check the MT5 terminal — is it still running and logged in?
2. Check internet connectivity.
3. Run `.\scripts\health_check.ps1` to verify status.
4. If the watchdog has blocked execution, manually verify the connection is restored before resuming.
5. Restart the bot with `.\scripts\restart.ps1` if needed.

## IPC Timeout

1. Verify the MT5 terminal and Python process are running under the same Windows user context.
2. Check that MT5 IPC is not blocked by firewall or antivirus.
3. Restart the MT5 terminal and the bot.
4. Run `.\scripts\health_check.ps1`.

## Market Data Failure

1. Check if quotes are being received (dashboard Market Monitoring section).
2. Verify MT5 terminal is connected and subscribed to symbols.
3. Check for scheduled market closures (weekends/holidays are not failures).
4. If data is stale for > 60 seconds, the watchdog flags it.
5. Restart the bot if data does not resume.

## Risk Engine Failure

1. Check the Risk Monitoring section of the dashboard.
2. Verify the risk engine is available and not locked.
3. Check circuit breaker status — if locked, investigate the cause before unlocking.
4. If the risk engine is unavailable, new demo execution is blocked (safety feature).
5. Restart the bot after resolving the issue.

## Database Failure

1. Check the execution journal at `.execution_journal/journal.jsonl`.
2. Run `.\scripts\health_check.ps1`.
3. If the journal is corrupted, restore from the most recent backup:
   `.\scripts\restore.ps1 -BackupId <id> -Confirm`
4. Never delete existing trading history.

## Execution Timeout

1. Check the execution journal for UNKNOWN or SUBMITTED states.
2. **Never automatically resend an uncertain order.**
3. Reconcile with broker orders, positions, and deals.
4. Preserve UNKNOWN states until manually resolved.
5. Require explicit recovery authorization before resuming.

## Partial Fill

1. Check the execution journal for PARTIALLY_FILLED states.
2. Verify the remaining volume with the broker.
3. Do not automatically submit a new order for the remaining volume without reconciliation.
4. Monitor the position until fully filled or cancelled.

## UNKNOWN Order Submission

1. Check the execution journal for UNKNOWN states.
2. Reconcile with broker orders, positions, and deals history.
3. If the order may have executed, block duplicate submission until resolved.
4. Require explicit recovery authorization.
5. Never blindly retry.

## Risk Circuit Breaker

1. Check which circuit breaker is triggered (emergency stop, daily loss, drawdown, etc.).
2. Investigate the root cause before resetting.
3. **Persistent lockouts survive application restarts.**
4. Reset requires explicit authorization — never auto-cleared.
5. Emergency stop blocks new entries but never auto-liquidates positions.

## Application Crash

1. Check `logs/trading_bot.log` and `logs/audit_errors.log` for the crash reason.
2. Run `.\scripts\health_check.ps1`.
3. Recover using `.\scripts\start.ps1` — the recovery manager will:
   - Load the execution journal
   - Identify unresolved submissions
   - Reconcile with the broker
   - Preserve UNKNOWN states
4. Do not resume trading until unresolved executions are reviewed.

## Server Reboot

1. After reboot, verify MT5 terminal is running and logged in.
2. Verify external Python API trading permission is still enabled.
3. Run `.\scripts\start.ps1` to start the bot.
4. Check that unresolved executions from before the reboot are reconciled.
5. Verify health status is `RUNNING` or `DEGRADED`.

## Backup and Restore

### Create a Backup

```
.\scripts\backup.ps1
```

### List Backups

```
.\scripts\restore.ps1 -List
```

### Restore from Backup

```
.\scripts\restore.ps1 -BackupId backup-20261126-120000 -Confirm
```

**Warning:** Restore overwrites existing files. Confirm before proceeding.
Backups never include `.env` or secret files.

## Manual Emergency Stop

1. The emergency stop can be activated via the monitoring dashboard or
   programmatically.
2. When activated, new entries are blocked immediately.
3. **Existing positions are NOT closed.**
4. To resume: investigate the cause, then deactivate the emergency stop with
   explicit authorization.
5. Persistent lockouts survive restarts — reset requires explicit authorization.

---

## Pre-Restart Checklist

Before restarting the application, verify:

- [ ] Execution journal has been reviewed for unresolved entries
- [ ] No UNKNOWN execution states require manual resolution
- [ ] MT5 terminal is running and connected
- [ ] External Python API trading permission is enabled
- [ ] Configuration is valid (PAPER mode, no LIVE settings)
- [ ] No circuit breakers are locked (or have been intentionally reset)
- [ ] No emergency stop is active (or has been intentionally deactivated)
