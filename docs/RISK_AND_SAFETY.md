# Risk and Safety — Forex Trading Bot

Mandatory safety policy for the Forex trading bot project. These rules apply to
all phases and must not be weakened without explicit review.

## 1. Live trading is disabled by default

- `TRADING_MODE=simulation` and `ENABLE_LIVE_TRADING=false` by default.
- `TradeExecutionEngineImpl` rejects every order while `live_locked` is true.
- Live mode remains locked until a later development phase and only after
  extensive demo/paper validation.

## 2. No real orders in development

Phase 1 places no real orders. The `MockBrokerAdapter` simulates execution
without contacting any market or broker. Phase 3's MT5 adapter is read-only:
`place_order` and `close_order` are hard-disabled (rejected with error 403);
`get_orders` / `get_positions` perform genuine read-only retrieval via
`orders_get()` / `positions_get()`; `order_send` / `order_check` are never
called.

## 3. No credentials stored

- Do not request, log, or store broker passwords, API keys, or account details.
- `.env` is git-ignored and must never be committed.
- Never hardcode credentials in source code.
- The MT5 integration reuses a **manually authenticated** desktop terminal; the
  Python application never handles the broker password.
- Never print or log passwords, login numbers, balances, or personal account
  information. Diagnostics show only a safe account summary (mode, server,
  currency, trading-allowed flag).

## 4. Mock broker for initial testing

All initial testing uses `MockBrokerAdapter` and mocked MT5 unit tests. Real
MT5/PuPrime connectivity is validated manually, on demo first, via the
diagnostics script.

## 5. Configuration flags

- `TRADING_MODE`: `simulation` | `demo` | `live`
- `ENABLE_LIVE_TRADING`: master kill-switch (boolean)
- `LOG_LEVEL`: `DEBUG` | `INFO` | `WARNING` | `ERROR` | `CRITICAL`
- `MT5_TERMINAL_PATH`: optional explicit path to the MT5 terminal executable

### Phase 9 execution configuration (fail-closed)

- `EXECUTION_MODE`: `PAPER` (default) | `DEMO_MANUAL` | `DEMO_AUTO`; `LIVE`/`REAL`
  rejected.
- `DEMO_EXECUTION_ENABLED`: must be `true` for any demo submission.
- `DEMO_MANUAL_APPROVAL_REQUIRED`: `true` by default; per-order user approval.
- `DEMO_AUTOMATIC_ENABLED`: `false` by default; DEMO_AUTO also needs a CLI flag.
- `MT5_ALLOWED_DEMO_SERVER`: exact permitted demo server (no partial matching).
- `MT5_ALLOWED_BROKER_COMPANY`: exact permitted broker company (where required).
- `MT5_MAGIC_NUMBER`: unique configured MT5 magic number (> 0 for demo).
- `MAX_DEMO_ORDERS_PER_DAY`, `MAX_DEMO_OPEN_POSITIONS`, `MAX_DEMO_ORDER_VOLUME`,
  `MAX_DEMO_DAILY_RISK`: execution limits (0 = unset; validated when set).
- `DEMO_APPROVAL_TTL_SECONDS`: manual approval time-to-live.
- Missing critical values fail closed; `.env` is git-ignored; no passwords stored.


## 6. Centralized risk management

- A single `RiskManager` interface governs position sizing, stop-loss,
  take-profit, exposure, and daily-loss limits.
- The trade execution engine consults the risk manager before routing orders.

## 7. Fail-safe behavior

- Missing market data → do not trade; log and skip.
- Connection failure → retry with backoff, then halt; log clearly.
- Abnormal spreads → reject orders beyond a configured max-spread threshold.
- Unexpected errors → caught at boundaries, logged, and do not crash the bot.
- MT5 package not installed → diagnostics and provider fail safely; the project
  still runs and all unit tests pass without it.
- MT5 terminal not running → diagnostics fail safely with actionable guidance.

## 8. No profitability promises

- No win-rate or guaranteed-profitability claims, ever.
- Backtest results are not predictive of future performance.

## 9. Legitimate data sources only

- No scraping or bypassing access restrictions.
- Economic calendar data must come from legitimate sources whose terms of use
  are reviewed before integration.

## 10. No unverified broker assumptions

- Symbol availability, lot sizes, point values, and spreads must be verified
  against PuPrime (demo) before being hardcoded.
- Broker-specific settings are configurable and verified later.

## 11. DEMO-ONLY SAFETY LOCK (Phase 3, mandatory)

- The MT5 adapter accepts **demo accounts only**.
- Before any market data is retrieved, `account_info().trade_mode` is checked
  using the official enumeration: `ACCOUNT_TRADE_MODE_DEMO=0` (accepted),
  `ACCOUNT_TRADE_MODE_CONTEST=1` (rejected), `ACCOUNT_TRADE_MODE_REAL=2`
  (rejected). Missing account information fails safely (`MT5AccountError`).
- The adapter never automatically switches accounts, never attempts live
  account login (never calls `mt5.login()`), and never enables live trading.
- The account information API is used only to verify demo status; the complete
  account object is never logged.
- The existing execution safety lock (`live_locked`) remains intact.

## 12. Data provenance and labeling

- MT5 market data is tagged `DataSource.LIVE` and flows through the Phase 2
  validator/processor — never mislabeled as simulated or historical CSV data.
- Incomplete/forming candles are never silently classified as complete; the
  completed-candle-only mode starts at MT5 position 1.
- Historical CSV data is never overwritten or mislabeled by broker data.

## 13. Phase 5 — Strategy Engine Safety

Phase 5 is a signal-generation phase only. The following restrictions apply:

- Strategies produce `Signal` objects (LONG/SHORT/NONE) — never `OrderRequest`.
- No `place_order`, `close_order`, `order_send`, or `order_check` calls.
- No order placement, modification, or closing of any kind.
- Strategies cannot access broker execution code or account state.
- `ENABLE_LIVE_TRADING` remains `False`; `live_locked` stays active.
- No automatic account switching or live login.
- All signal data source provenance is preserved
  (`DataSource.SIMULATED`/`HISTORICAL`/`LIVE`).
- Signal scores or weights are NOT presented as probabilities of winning
  unless separately calibrated and statistically validated.
- Conflicting signals are reported, not resolved by forcing a trade decision.
- One failed strategy does not crash the system (fault isolation).
- Errors are logged; they are never silently suppressed.

## 14. Phase 6 — Risk Management Engine Safety

Phase 6 is a risk-evaluation-only phase. It calculates, validates, and reports
on proposed trade signals. The following restrictions apply:

- No `place_order`, `close_order`, `order_send`, or `order_check` calls — ever.
- No order placement, modification, or closing of any kind.
- No automatic liquidation or position closing.
- A `RISK_APPROVED` decision is hypothetical only — it passed configured risk
  checks but does **not** authorize execution. Phase 6 does not execute
  risk-approved proposals.
- Position sizing uses Decimal arithmetic; volume is rounded **DOWN** to the
  broker lot step and is never rounded up beyond the configured monetary risk
  budget. Volume below the broker minimum lot → rejected.
- Missing essential instrument specifications (contract size, tick value,
  account-currency conversion rate) are never guessed — rejected with a clear
  explanation.
- Stop-loss: LONG below entry / SHORT above entry; positive distance; min/max
  distance and %-of-entry limits enforced. A technical invalidation level is
  never silently moved to force an acceptable position size.
- Take-profit: LONG above entry / SHORT below entry; minimum reward-to-risk
  enforced.
- Daily loss: starting-reference equity/balance; deposits/withdrawals are
  excluded from PnL (they are not profit/loss); missing account info is never
  treated as zero losses.
- Drawdown: equity & balance high-watermarks are persisted to disk so a restart
  cannot reset protection limits; unavailable state fails safely.
- Circuit breakers: lockouts have trigger timestamps and lockout-until; they
  persist across restarts and require an explicit authorized reset — never
  auto-cleared.
- Portfolio exposure: max positions, portfolio risk, per-instrument and
  per-asset-class limits, directional exposure enforced.
- Correlation: Pearson correlation with configurable window/threshold;
  insufficient data does not cause rejection unless policy requires it.
- Margin: required vs free margin and margin-usage limits enforced; missing
  leverage/specs fail safely rather than inventing values.
- `ENABLE_LIVE_TRADING` remains `False`; `live_locked` stays active.
- No live trading, no automatic account switching, no broker credentials stored.

## 15. Phase 7 — News & Economic Calendar Engine Safety

Phase 7 is a **news/risk-information-only** phase. It collects, normalizes and
evaluates economic-calendar events and news, and communicates event-related
restrictions to the Phase 6 risk engine. The following restrictions apply:

- No `place_order`, `close_order`, `order_send`, or `order_check` calls — ever.
- No order placement, modification, or closing; no trade execution.
- No live trading, no automatic account switching, no broker credentials stored.
- News is passed to the risk engine as an **optional** `NewsRiskContext`; when
  absent (`None`), no news gate applies and all prior behavior is unchanged.
- Blocking/uncertain/unavailable news windows (`BLOCK_NEW_ENTRIES`,
  `EVENT_TIME_UNCERTAIN`, `NEWS_DATA_UNAVAILABLE`) reject new entries per the
  configured unavailable policy; `NEWS_CAUTION` only warns.
- Importance is **never** inferred from an event name; it comes from provider
  data (or is `UNKNOWN`).
- Missing actual/forecast/previous values and unresolved event times are never
  fabricated; unresolved times are flagged (EVENT_TIME_UNCERTAIN), not guessed.
- MQL5 economic-calendar timestamps use **trading-server time**; they are
  converted to UTC only when a verified server timezone is configured
  (DST-aware via `tzdata`). Otherwise the time is treated as unresolved.
- Historical/backtest queries are leakage-safe: future information is not used.
- Simulated providers are explicitly labeled `is_simulated=True` and never
  presented as genuine data.
- Economic-calendar/news data comes only from legitimate sources whose terms of
  use are reviewed; no scraping or bypassing access restrictions. External
  API/RSS providers are interfaces only; credentials are read from environment
  variables, never committed.
- `ENABLE_LIVE_TRADING` remains `False`; `live_locked` stays active.

## 16. Phase 8 — Backtesting Engine Safety

Phase 8 is a **simulation-only** phase. It replays historical data through the
existing indicators, strategies, risk, and news engines and never places real or
demo orders. The following restrictions apply:

- No `place_order`, `close_order`, `order_send`, or `order_check` calls — ever.
  No broker connection is made; execution is entirely internal to the simulator.
- A backtest fill is simulated at the next bar; entries never fill at the signal
  bar's price (no look-ahead). Indicators and strategies see only candles with
  `ts <= now`; news uses `events_as_of(now)`.
- Ambiguous stop-loss / take-profit hits (both levels within one bar) are resolved
  by the configured conservative default (stop-first) and are flagged, never
  silently assumed favorable.
- Transaction costs (spread, slippage, commission, swap) are modeled explicitly
  and never hidden; missing specs are not fabricated — trades may be rejected.
- Risk checks run at simulated time (`evaluate_signal(now=ts)`), so staleness and
  daily-loss resets reflect the bar clock, not wall-clock `datetime.now()`.
- Invalid/incomplete input bars are flagged and labeled `DataSource.SIMULATED`;
  missing data is preserved, never filled with fabricated prices.
- Results are hypothetical and not predictive of future performance; small-sample
  metrics (fewer than ~30 trades) are flagged as low-confidence.
- `ENABLE_LIVE_TRADING` remains `False`; `live_locked` stays active.
- No live trading, no automatic account switching, no broker credentials stored.

## 18. Phase 9 — Advanced Demo Trading & Execution Engine Safety

Phase 9 introduces controlled **demo-only** order execution to the PU Prime MT5
DEMO account. REAL / CONTEST / LIVE execution is permanently rejected.

Mandatory restrictions:

- **PAPER mode is the permanent default.** `PaperExecutionAdapter` simulates
  fills and never calls `order_send()` / `order_check()`;
  `can_submit_orders()` is `False`.
- **Only `DemoMT5ExecutionAdapter` may call MT5 trading functions**
  (`order_check`, `order_send`, `positions_get`, `orders_get`, `history_*`).
  Strategy, indicator, news, risk and backtesting modules never access the
  order API.
- **REAL and CONTEST accounts are always rejected.** LIVE mode does not exist.
- **Demo-account identity is reverified before every order-related request:**
  `trade_mode == DEMO`, exact `MT5_ALLOWED_DEMO_SERVER` match (no partial
  matching), `MT5_ALLOWED_BROKER_COMPANY` match (where configured), terminal
  connected, terminal trade permissions enabled, external Python API trading
  permission enabled when required.
- **Account identity binding** detects changes to the connected demo account or
  server; a changed account stops execution and requires explicit revalidation.
  Never call `mt5.login()` automatically; never save broker passwords; never
  switch accounts automatically.
- **`RISK_APPROVED` from Phase 6 is mandatory** and is never overridden; volume
  is never increased beyond the approved risk calculation; stop-loss is never
  auto-widened.
- **Two-stage authorization:** Stage A pre-trade validation (account, DEMO,
  mode, signal, risk, market/specs, volume/SL/TP, margin, `order_check()`
  preflight, execution preview); Stage B manual approval (DEMO_MANUAL) via a
  one-time, time-limited challenge bound to the exact order fingerprint —
  invalidated if any parameter changes — with revalidation immediately before
  `order_send()`.
- **DEMO_AUTO is hard-disabled by default** and requires both environment
  enablement (`DEMO_AUTOMATIC_ENABLED=true`) and an explicit CLI activation
  flag.
- **Submission intent is journaled before `order_send()`.** Timeouts produce an
  `UNKNOWN` state and are **never blindly retried**; broker reconciliation is
  required first.
- **Execution state machine** treats a non-null `order_send()` result as **not**
  proof of a fill; `PLACED` ≠ `FILLED`; partial fills handled explicitly.
- **Emergency stop** blocks new entries; never auto-liquidates positions; all
  lockouts persist across restarts and require explicit authorization to reset.
- **No broker passwords or login identifiers are stored or logged**; `.env` is
  git-ignored; `live_locked` remains active.

## 20. Phase 10 — Monitoring, Reliability and Deployment Safety

Phase 10 adds operational reliability, monitoring, and deployment preparation.
All safety rules from Phases 1–9 continue to apply.

Mandatory restrictions:

- **PAPER mode is the permanent default for deployment.**
  `EXECUTION_MODE=PAPER`, `DEMO_EXECUTION_ENABLED=false`,
  `DEMO_AUTOMATIC_ENABLED=false`.
- **LIVE mode is unavailable.** `ENABLE_LIVE_TRADING` remains `false`.
- **Deployment is not authorization to trade.** A successful deployment does
  not permit any order submission.
- **DEMO execution remains disabled on deployment** until separately authorized.
- **Monitoring dashboard is read-only and localhost-only** (`127.0.0.1`).
  No order submission controls; no sensitive account identifiers displayed.
- **Alerts never contain secrets.** Credentials come from environment variables
  only; notification messages are redacted.
- **Recovery never removes persistent emergency stops or risk lockouts.**
  Lockouts survive application restarts.
- **Never automatically resend an uncertain order.** UNKNOWN execution states
  are preserved until manually reconciled.
- **Backup files never contain secrets.** `.env`, credentials, and keys are
  excluded from all backups.
- **Windows VPS deployment requires MT5 desktop terminal under the same user
  context.** MT5 Virtual Hosting cannot host this separate Python process.
- **CI pipeline never requires broker credentials, MT5 terminal, or real
  account connections.** All CI tests are safe and deterministic.

## 21. Escalation

If any of these rules conflicts with a planned feature, pause implementation
and review before proceeding.
