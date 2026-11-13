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
without contacting any market or broker.

## 3. No credentials stored

- Do not request, log, or store broker passwords, API keys, or account details.
- `.env` is git-ignored and must never be committed.
- Never hardcode credentials in source code.

## 4. Mock broker for initial testing

All initial testing uses `MockBrokerAdapter`. MT5/PuPrime integration comes
later, on demo first.

## 5. Configuration flags

- `TRADING_MODE`: `simulation` | `demo` | `live`
- `ENABLE_LIVE_TRADING`: master kill-switch (boolean)
- `LOG_LEVEL`: `DEBUG` | `INFO` | `WARNING` | `ERROR` | `CRITICAL`

## 6. Centralized risk management

- A single `RiskManager` interface governs position sizing, stop-loss,
  take-profit, exposure, and daily-loss limits.
- The trade execution engine consults the risk manager before routing orders.

## 7. Fail-safe behavior

- Missing market data → do not trade; log and skip.
- Connection failure → retry with backoff, then halt; log clearly.
- Abnormal spreads → reject orders beyond a configured max-spread threshold.
- Unexpected errors → caught at boundaries, logged, and do not crash the bot.

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

## 11. Escalation

If any of these rules conflicts with a planned feature, pause implementation
and review before proceeding.
