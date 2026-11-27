# Monitoring — Forex Trading Bot (Phase 10)

This document describes the monitoring, alerting, reliability, and observability
architecture of the Automated Forex Trading Bot.

---

## Overview

The monitoring system provides:

- **Application lifecycle management** — explicit states (INITIALIZING →
  STARTING → RUNNING → DEGRADED → STOPPING → STOPPED → FAILED → LOCKED)
- **System health monitoring** — broker/MT5, market data, strategy engine,
  risk engine, news engine, execution engine
- **Heartbeat and watchdog** — detects freezes, disconnects, stalls, and
  service unavailability
- **Safe recovery** — journal reconciliation after crashes, bounded reconnection
- **Read-only monitoring dashboard** — localhost-only HTTP dashboard
- **Alerts and notifications** — email, Telegram, webhook, log output
- **Structured logging and audit trails** — JSON audit events with correlation IDs
- **Backup and restore** — durable execution journal and configuration backups

---

## Application Lifecycle

### Lifecycle States

| State | Description |
|-------|-------------|
| `INITIALIZING` | Application is starting, validating configuration |
| `STARTING` | Dependencies are being initialized |
| `RUNNING` | All critical dependencies available, application operational |
| `DEGRADED` | Some dependencies unavailable, limited functionality |
| `STOPPING` | Graceful shutdown in progress |
| `STOPPED` | Application has stopped cleanly |
| `FAILED` | Startup or runtime failure |
| `LOCKED` | Application locked (manual or safety lock) |

The application must not report `RUNNING` when critical dependencies are
unavailable. Startup never silently switches execution modes.

### Process Lock

A single execution-owner lock prevents two bot instances from running
simultaneously. The lock is released during graceful shutdown.

---

## System Health Monitoring

### Subsystems Monitored

| Subsystem | What's Checked |
|-----------|---------------|
| **Broker / MT5** | Terminal connection, account mode (DEMO only), server identity, broker company, trade permissions |
| **Market Data** | Quote freshness, data gaps, invalid candles, provider availability |
| **Strategy Engine** | Enabled strategies, signal processing, errors, duration |
| **Risk Engine** | Availability, circuit breaker status, daily loss, drawdown, exposure |
| **News Engine** | Provider health, calendar freshness, active restrictions |
| **Execution Engine** | Execution mode, pending approvals, submitted orders, fills, rejections, UNKNOWN states, reconciliation |

### Health Status Values

- `healthy` — Subsystem operating normally
- `degraded` — Subsystem operating with reduced capability
- `unhealthy` — Subsystem not functioning
- `unknown` — Health status could not be determined

---

## Heartbeat and Watchdog

### Heartbeat

Every critical subsystem reports:
- Current status (alive/stale/dead/unknown)
- Last successful operation time
- Last heartbeat time
- Failure count
- Processing latency
- Last error (if applicable)

### Watchdog

The watchdog detects:
- Application freeze
- Unresponsive worker
- Stalled market data
- MT5 disconnection
- Failed strategy processing
- Risk service unavailability
- News provider failure
- Execution queue backlog
- Reconciliation failure

**Watchdog safety rules:**
- Configurable timeouts
- No alerts for ordinary scheduled market closures
- Weekends and market holidays are not system failures
- **The watchdog never automatically authorizes new trading**
- If Risk Engine, Account Identity, or Reconciliation is unavailable, new demo execution is blocked

---

## Safe Recovery

After an execution timeout or application crash:

1. Load the persistent execution journal
2. Identify unresolved submissions
3. Reconcile with actual broker orders, positions, and deals
4. Preserve UNKNOWN execution states until resolved
5. **Never automatically resend an uncertain order**
6. Require explicit recovery authorization when ambiguity remains

**Recovery safety rules:**
- Bounded MT5 reconnection with exponential backoff + jitter
- Recovery never removes persistent emergency stops or risk lockouts
- If critical services are unavailable, new demo execution is blocked

---

## Monitoring Dashboard

### Architecture

- Lightweight HTTP dashboard using Python `http.server` (stdlib)
- **Read-only** — no order submission, modification, or cancellation
- **Localhost-only binding** — `127.0.0.1:8765` by default
- No unauthenticated public exposure

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | HTML dashboard page |
| `GET /api/health` | System health JSON |
| `GET /api/status` | Application status JSON |
| `GET /api/execution` | Execution summary JSON |

### Dashboard Sections

- **Overview** — application status, execution mode, server, MT5 connectivity, strategies, instruments
- **Market Monitoring** — bid/ask quotes, spread, latest candle, session status, data freshness
- **Strategy Monitoring** — enabled strategies, recent signals, direction, timestamps, status, rejection reasons
- **Risk Monitoring** — equity, balance, daily PnL, drawdown, risk utilization, exposure, circuit breakers
- **News Monitoring** — upcoming events, currencies, impact levels, forecast/actual values, restrictions
- **Execution Monitoring** — mode, pending approvals, execution states, completed trades, partial fills, rejections, UNKNOWN submissions, reconciliation warnings, bot positions
- **System Health** — CPU, memory, disk, process status, worker health, recent errors, logging status

### Security

- Default binding: localhost only
- No order submission controls in the dashboard
- No sensitive account identifiers or passwords displayed
- Optional authentication token support

---

## Alerts and Notifications

### Alert Categories

| Severity | Examples |
|----------|----------|
| **Critical** | Account mode changed, execution safety violation, emergency stop, unresolved order, risk persistence failure, database corruption, application termination |
| **High** | MT5 disconnected, risk engine unavailable, reconciliation failure, market data stalled, excessive drawdown, daily loss limit |
| **Medium** | High-impact news approaching, strategy failure, increased spreads, provider degradation |
| **Informational** | Application startup, shutdown, daily report, successful sync, completed demo trade |

### Providers (All Optional)

| Provider | Configuration | Status |
|----------|--------------|--------|
| Log | Always available | Local log output |
| Email | SMTP host, port, user, password, from, to | Optional |
| Telegram | Bot token, chat ID | Optional |
| Webhook | URL, secret | Optional |

### Safety Features

- Alert deduplication (configurable time window)
- Configurable rate limiting
- Notification failure handling
- Alert history and delivery status
- **Never reports an alert as delivered without confirmed delivery**
- **Never sends secrets in notification messages**
- Credentials in environment variables only

---

## Structured Logging and Audit Trails

### Log Types

- Application logs
- Market data logs
- Strategy logs
- Risk logs
- News logs
- Execution logs
- Broker connection logs
- Security audit logs

### Audit Event Fields

Every important execution event contains:
- Event ID
- Timestamp
- Component
- Severity
- Execution or signal reference (where applicable)
- Correlation ID
- Result
- Error classification

### Log Rotation

- Rotating file handler: 5 MB max, 3 backups
- Separate error log: `audit_errors.log`
- Retention: 30 days (configurable)

### Sensitive Data Redaction

**Never logs:** broker passwords, API keys, authentication tokens, unnecessary account identifiers.

Automatic redaction of: API keys, bot tokens, passwords, secrets, tokens, credit card numbers.