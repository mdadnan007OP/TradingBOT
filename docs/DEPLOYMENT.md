# Deployment — Forex Trading Bot (Phase 10)

This document describes how to deploy the Automated Forex Trading Bot to a
Windows VPS or AWS EC2 Windows environment. The application runs as a separate
Python process communicating with a MetaTrader 5 (MT5) desktop terminal.

**Important:** This is deployment preparation documentation only. No cloud
infrastructure is provisioned, no services are purchased, and no actual running
trading instance is deployed automatically.

---

## Deployment Safety Modes (Mandatory)

The default deployment uses:

```
EXECUTION_MODE=PAPER
DEMO_EXECUTION_ENABLED=false
DEMO_AUTOMATIC_ENABLED=false
```

- **PAPER mode is the permanent default.** No broker order submission occurs.
- **DEMO execution is disabled on deployment** until separately authorized.
- **LIVE mode is unavailable.** `ENABLE_LIVE_TRADING` remains `false`.
- A successful deployment is **not** authorization to trade.

---

## Supported Deployment Architectures

### A. Local Development (Recommended for Testing)

- Existing Windows development computer
- PAPER mode
- Debug logging
- Mock and historical data
- No actual broker trading

### B. Windows VPS (Primary Production Architecture)

A conventional Windows VPS is the recommended deployment target because the
application depends on an external Python process communicating with an MT5
desktop terminal.

**MT5 Virtual Hosting is NOT supported** for this separate Python application.
MetaTrader's native virtual hosting supports Expert Advisors and indicators
only; scripts cannot be transferred and DLL calls are prohibited. The Python
application must run on a conventional Windows VPS or EC2 instance with the
MT5 desktop terminal installed under the same user context.

### C. AWS EC2 Windows (Optional)

See the AWS deployment section below.

---

## Windows VPS Deployment Guide

### Prerequisites

- Windows Server 2019 or 2022 (64-bit)
- Python 3.10+ (3.13 recommended)
- MetaTrader 5 desktop terminal installed
- PU Prime demo terminal account
- Remote Desktop (RDP) access with least-privilege user

### 1. Python Setup

```powershell
# Install Python 3.13 from https://www.python.org/downloads/windows/
# During installation, check "Add Python to PATH"

# Verify installation
python --version
pip --version

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -e .[dev]
```

### 2. MT5 Desktop Installation

1. Download and install MetaTrader 5 from the official MetaQuotes website.
2. Open MT5 and log in to your PU Prime demo account.
3. Verify the account is DEMO (not REAL or CONTEST).
4. Enable external Python API trading:
   - **Tools → Options → Expert Advisors**
   - Check: "Allow Algo Trading"
   - Check: "Allow external Python API trading" (this must be explicitly enabled by the user)
   - **Do not change this automatically during deployment.**
5. Note the exact demo server name (e.g., `PUPrime-Demo`) — configure this in `MT5_ALLOWED_DEMO_SERVER`.

### 3. Project Installation

```powershell
# Clone the repository
git clone https://github.com/mdadnan007OP/TradingBOT.git
cd TradingBOT

# Copy environment template
copy .env.example .env

# Edit .env with your configuration (never commit .env)
# Set: EXECUTION_MODE=PAPER
# Set: DEMO_EXECUTION_ENABLED=false
# Set: MT5_ALLOWED_DEMO_SERVER=<your-verified-demo-server>
# Set: MT5_ALLOWED_BROKER_COMPANY=<your-broker-company>
# Set: MT5_MAGIC_NUMBER=<unique-magic-number>
```

### 4. Configuration

Critical environment variables (set in `.env`, never commit):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `EXECUTION_MODE` | Yes | `PAPER` | `PAPER` \| `DEMO_MANUAL` \| `DEMO_AUTO` |
| `DEMO_EXECUTION_ENABLED` | Yes | `false` | Must be `true` for any demo submission |
| `DEMO_AUTOMATIC_ENABLED` | Yes | `false` | Must be `true` for DEMO_AUTO |
| `DEMO_MANUAL_APPROVAL_REQUIRED` | No | `true` | Per-order user approval |
| `MT5_ALLOWED_DEMO_SERVER` | Yes (for DEMO) | `` | Exact demo server name (no partial matching) |
| `MT5_ALLOWED_BROKER_COMPANY` | No | `` | Exact broker company name |
| `MT5_MAGIC_NUMBER` | Yes (for DEMO) | `0` | Unique MT5 magic number (> 0) |
| `LOG_LEVEL` | No | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |
| `LOG_DIR` | No | `logs` | Log directory |

### 5. Safe Startup and Shutdown

Use the provided PowerShell scripts in `scripts/`:

```powershell
# Start the bot (PAPER mode by default)
.\scripts\start.ps1

# Stop the bot gracefully (never liquidates positions)
.\scripts\stop.ps1

# Restart the bot
.\scripts\restart.ps1

# Health check
.\scripts\health_check.ps1

# Backup trading data
.\scripts\backup.ps1

# Restore from backup (requires -Confirm)
.\scripts\restore.ps1 -BackupId backup-20261126-120000 -Confirm
```

**start.ps1** prevents duplicate instances via a process lock, validates
configuration, and starts the bot in PAPER mode.

**stop.ps1** performs a graceful shutdown: blocks new entries, waits for the
process to exit, and never closes positions.

### 6. Monitoring and Logging

- Application logs: `logs/trading_bot.log` (rotating, 5 MB max, 3 backups)
- Audit logs: `logs/audit.log` (structured JSON events)
- Monitoring dashboard: `http://127.0.0.1:8765` (localhost-only, read-only)
  - Enable with: `MONITORING_DASHBOARD_ENABLED=true`
- Execution journal: `.execution_journal/journal.jsonl` (durable, append-only)

### 7. Backup and Recovery

```powershell
# Create a backup
.\scripts\backup.ps1

# List available backups
.\scripts\restore.ps1 -List

# Restore from backup (explicit confirmation required)
.\scripts\restore.ps1 -BackupId backup-20261126-120000 -Confirm
```

Backups include: execution journal, risk breakers, config template, logs.
Backups **never** include `.env` or other secret files.

Retention: max 10 backups, 30 days retention (configurable).

---

## AWS EC2 Windows Deployment Guide

### Instance Selection

- **OS:** Windows Server 2019 or 2022 (64-bit)
- **Instance type:** t3.medium or larger (2 vCPU, 8 GB RAM minimum)
- **Storage:** 100 GB+ gp3 (for logs, backups, execution journal)
- **Tenancy:** Dedicated or default (no special requirements)

### Network and Security

- **Security Group:** Restrict inbound RDP (port 3389) to specific IP ranges only.
- **No public internet exposure** for the monitoring dashboard (localhost-only binding).
- **No public internet exposure** for RDP — use AWS Systems Manager Session Manager or a VPN bastion.

### IAM and Permissions

- Use an IAM role with least-privilege permissions.
- Do not store AWS credentials in `.env` or source code.
- Use AWS Systems Manager Parameter Store or Secrets Manager for any required secrets.

### Setup Steps

1. Launch the Windows EC2 instance.
2. Connect via RDP (restricted to your IP range).
3. Install Python 3.13 and MetaTrader 5 desktop terminal.
4. Follow the Windows VPS deployment steps above (sections 1–7).
5. Configure Windows Firewall to block all inbound traffic except RDP from your IP.
6. Set up Windows Task Scheduler to run `scripts\start.ps1` on logon if desired.

**Task Scheduler logon behavior:** Configure the task to run only when the user
is logged on (interactive session) to ensure MT5 IPC compatibility. Do not
configure "Run whether user is logged on or not" unless MT5 IPC has been verified
in that context.

---

## Process Management

Do **not** install the Python application or interactive MT5 terminal as Windows
Services without verifying session and IPC compatibility first. MT5 IPC requires
an interactive desktop session.

Recommended approach:
- Run MT5 desktop terminal and the Python bot under the same Windows user
  context (interactive logon).
- Use Windows Task Scheduler with "Run only when user is logged on" for
  auto-start on boot.
- Use the provided PowerShell scripts for manual start/stop/restart.

---

## Security Checklist

- [ ] `.env` is not committed to Git (git-ignored)
- [ ] No broker passwords in source code or logs
- [ ] Dashboard binds to 127.0.0.1 only (localhost)
- [ ] MT5 external Python API trading permission explicitly enabled by user
- [ ] `EXECUTION_MODE=PAPER` by default
- [ ] `DEMO_EXECUTION_ENABLED=false` by default
- [ ] `DEMO_AUTOMATIC_ENABLED=false` by default
- [ ] RDP restricted to specific IP ranges
- [ ] Least-privilege Windows user account
- [ ] Backups exclude secret files
- [ ] Log rotation configured (5 MB max, 3 backups)

---

## Known Limitations

- The application depends on an MT5 desktop terminal running under the same
  user context. MT5 Virtual Hosting cannot host this separate Python process.
- PAPER mode is simulated and not indicative of real performance.
- DEMO execution requires explicit authorization and manual approval
  (DEMO_MANUAL mode).
- No live trading is supported in this phase.