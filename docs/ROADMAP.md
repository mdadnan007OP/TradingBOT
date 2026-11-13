# Development Roadmap — Forex Trading Bot

Phase 1 (complete): foundation. Subsequent phases build toward a production
ready MT5/PuPrime bot. Dates are targets only.

## Phase 1 — Foundation (DONE)

- Project folder structure
- Centralized config + `.env` support
- Data models (broker-agnostic)
- Logging (console + rotating file)
- Broker adapter interface + MockBrokerAdapter
- Trade execution engine with live-trade lock
- Engine interfaces for all 10 modules
- Application entry point
- Unit tests
- Documentation (README, architecture, roadmap, risk & safety)

## Phase 2 — MT5 Broker Adapter & Market Data

- Implement `Mt5BrokerAdapter` (MetaTrader 5) behind `BrokerAdapter`.
- Add connection, disconnection, account info, instruments, ticks, candles.
- Implement `MarketDataEngine` (collect/validate price & candle data).
- Add reconnection logic and fail-safe for connection failure.
- Verify broker specifications (symbol availability, lot sizes, point, spreads)
  with PuPrime on demo before assuming anything.
- Add config flags: `BROKER=mock|mt5`, `MT5_PATH`, `MT5_SERVER`, `MT5_LOGIN`.

## Phase 3 — Technical Indicator Engine

- Implement EMA, SMA, RSI, MACD, Bollinger Bands, ATR, ADX, Stochastic.
- `IndicatorEngine.compute(name, symbol, candles, **params)` contract.
- Unit tests per indicator against known values.

## Phase 4 — Strategy Engine

- `Strategy` ABC (`on_tick`, `on_candle`, `enabled`).
- `StrategyEngine` (register/enable/disable/dispatch).
- Starter strategies: EMA crossover, RSI mean-reversion, breakout (skeletons,
  clearly marked non-operational until backtested).

## Phase 5 — Risk Management Engine

- `RiskManager` ABC: `validate`, `compute_position_size`,
  `daily_loss_limit_reached`, `max_positions_reached`.
- Position sizing (% equity per trade), stop-loss/take-profit calculation.
- Daily loss limit, max concurrent positions, max exposure per symbol.
- Centralized risk interface used by `TradeExecutionEngine`.

## Phase 6 — News & Economic Calendar Engine

- `NewsEngine` ABC: upcoming events, `is_trading_allowed`,
  `minutes_to_next_high_impact_event`.
- Investigate legitimate economic calendar data sources and their terms of use
  before integrating (no scraping or bypassing access restrictions).
- Configurable trading restrictions around high-impact events (CPI, NFP, rate
  decisions).

## Phase 7 — Backtesting Engine

- `BacktestingEngine.run(symbol, candles)` evaluating strategies on history.
- Performance metrics: win rate, profit factor, drawdown, expectancy.
- No profitability guarantees; backtest results are not predictive.

## Phase 8 — Paper / Demo Trading Engine

- `PaperTradingEngine`: run strategies on live/demo data without real funds.
- Paper order tracking, equity curve, simulated SL/TP hits.

## Phase 9 — Monitoring & Reporting

- `MonitoringEngine`: record trades, errors, performance, system status.
- Logging, dashboards/reports, alerts.
- Performance reporting (equity curve, drawdown, trade log).

## Phase 10 — Live Trading (only after Phases 1–9 validated on demo)

- Unlock `ENABLE_LIVE_TRADING=true` only after extensive demo/paper validation.
- PuPrime live account connection (MT5).
- Real orders placed only with explicit user approval.
- Never promise win rate or guaranteed profitability.
