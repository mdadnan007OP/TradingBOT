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

## 14. Escalation

If any of these rules conflicts with a planned feature, pause implementation
and review before proceeding.
