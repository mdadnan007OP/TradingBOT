# Security — Forex Trading Bot (Phase 10)

This document describes the security architecture, hardening measures, and
security checklist for the Automated Forex Trading Bot.

---

## Security Principles

1. **Demo-only execution** — REAL / CONTEST / LIVE accounts are permanently rejected.
2. **PAPER mode is the default** — no broker order submission occurs by default.
3. **No secrets in source code** — all credentials come from environment variables.
4. **Fail-closed** — missing or invalid configuration blocks execution.
5. **Least privilege** — minimum permissions required for operation.
6. **No automatic trading** — DEMO_AUTO requires explicit env + CLI activation.
7. **Read-only dashboard** — no order submission controls, localhost-only.

---

## Configuration Security

### Environment Variables

All sensitive configuration is stored in environment variables, never in source
code. The `.env` file is git-ignored and must never be committed.

Critical variables (set in `.env`):

| Variable | Purpose | Security Note |
|----------|---------|---------------|
| `EXECUTION_MODE` | PAPER / DEMO_MANUAL / DEMO_AUTO | Defaults to PAPER |
| `DEMO_EXECUTION_ENABLED` | Enables demo submission | Must be explicitly `true` |
| `DEMO_AUTOMATIC_ENABLED` | Enables DEMO_AUTO | Must be explicitly `true` + CLI flag |
| `MT5_ALLOWED_DEMO_SERVER` | Permitted demo server | Exact match, no partial matching |
| `MT5_ALLOWED_BROKER_COMPANY` | Permitted broker company | Exact match |
| `MT5_MAGIC_NUMBER` | MT5 magic number | Unique per deployment |
| `MONITORING_DASHBOARD_AUTH_TOKEN` | Dashboard auth token | Optional |
| `MONITORING_EMAIL_SMTP_PASSWORD` | SMTP password | Optional |
| `MONITORING_TELEGRAM_BOT_TOKEN` | Telegram bot token | Optional |

### .env Protection

- `.env` is listed in `.gitignore` and must never be committed.
- Copy `.env.example` to `.env` and fill in values locally.
- Never share `.env` files.

---

## Account Identity Protection

Before every broker trading operation, the system verifies:

- MT5 terminal is connected
- Account trade mode is DEMO (REAL = 2, CONTEST = 1 rejected)
- Exact `MT5_ALLOWED_DEMO_SERVER` match (no partial string matching)
- `MT5_ALLOWED_BROKER_COMPANY` match (where configured)
- Terminal trade permissions enabled
- External Python API trading permission enabled (when required)
- Account identity has not changed since binding

**Account identity binding:**
- Local HMAC-based fingerprint (server + company, no raw login IDs)
- Stored only in Git-ignored runtime directory
- Never uploaded to GitHub
- Account change stops execution and requires explicit revalidation
- Never calls `mt5.login()` automatically
- Never saves broker passwords
- Never switches accounts automatically

---

## Dashboard Security

- **Default binding:** `127.0.0.1` (localhost only)
- **Read-only:** No order submission, modification, or cancellation
- **Optional authentication:** `MONITORING_DASHBOARD_REQUIRE_AUTH=true` with `MONITORING_DASHBOARD_AUTH_TOKEN`
- No sensitive account identifiers or passwords displayed
- Not exposed to the public internet

**If remote access is required:** implement explicitly secured access with
authentication and encrypted transport (e.g., VPN, SSH tunnel, or reverse proxy
with TLS). Never expose an unauthenticated dashboard publicly.

---

## Logging Security

### Sensitive Data Redaction

The following patterns are automatically redacted from log messages:

- API keys (`sk-...`)
- Telegram bot tokens (`bot123:...`)
- Passwords (`password=...`)
- Secret keys (`secret=...`)
- Tokens (`token=...`)
- Credit card numbers

**Never logs:** broker passwords, API keys, authentication tokens, unnecessary account identifiers.

### Log Files

- `logs/trading_bot.log` — application log (rotating, 5 MB, 3 backups)
- `logs/audit.log` — structured JSON audit events
- `logs/audit_errors.log` — error-level audit events

---

## Backup Security

Backups include:
- Execution journal (`.execution_journal/`)
- Risk breakers (`.emergency_stop/`)
- Config template (`.env.example`)
- Logs (`logs/`)

Backups **never** include:
- `.env` (contains secrets)
- `secrets.json`
- `credentials.json`
- SSH keys (`id_rsa`, `id_ed25519`)

Backups are stored as ZIP archives in `backups/` with retention limits.

---

## Secret Management

- No hardcoded credentials in source code
- All secrets read from environment variables
- `.env` is git-ignored
- CI pipeline checks for accidentally committed secret files
- Secrets never sent in notification messages (redacted before sending)

---

## Security Checklist

- [ ] `.env` is not committed to Git (git-ignored)
- [ ] No broker passwords in source code or logs
- [ ] Dashboard binds to 127.0.0.1 only (localhost)
- [ ] MT5 external Python API trading permission explicitly enabled by user
- [ ] `EXECUTION_MODE=PAPER` by default
- [ ] `DEMO_EXECUTION_ENABLED=false` by default
- [ ] `DEMO_AUTOMATIC_ENABLED=false` by default
- [ ] `LIVE`/`REAL` execution mode rejected
- [ ] RDP restricted to specific IP ranges (VPS deployment)
- [ ] Least-privilege Windows user account
- [ ] Backups exclude secret files
- [ ] Log rotation configured
- [ ] Alert deduplication and rate limiting enabled
- [ ] CI pipeline scans for committed secrets
- [ ] Emergency stops and risk lockouts persist across restarts

---

## Prohibited Actions

- Never commit secrets to Git
- Never expose MT5 passwords
- Never publish account identifiers
- Never expose an unprotected dashboard publicly
- Never disable execution safety locks
- Never automatically enable DEMO_AUTO
- Never implement LIVE trading
