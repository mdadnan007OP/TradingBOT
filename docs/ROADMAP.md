# Development Roadmap — Forex Trading Bot

Phase 1 (complete): foundation. Phase 2 (complete): Market Data Engine.
Phase 3 (complete): read-only MT5 integration (PU Prime demo connectivity).
Subsequent phases build toward a production-ready MT5/PuPrime bot.
Dates are targets only.

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

## Phase 2 — Market Data Engine (DONE)

- Universal instrument registry with multi-asset classes (Forex, metals, energy, indices, equities, crypto, other)
- Configurable instrument specifications (broker symbol mapping, price precision, tick/pip size, contract size, volume type, supported timeframes, market session)
- Provider interface: `MarketDataProvider` ABC
- Mock market data provider (simulated OHLC, seed-based, reproducible, clearly labeled `is_simulated=True`)
- Historical CSV provider (local file loading, column validation, optional volumes/spread)
- Data validation engine (session-aware: distinguishes expected market closures from unexpected gaps)
- Market session calendars (Forex weekend, crypto 24/7, equity daily hours, configurable sessions)
- Data processing engine (sort, deduplicate, filter by symbol/timeframe/date-range, missing interval detection)
- Candle quality metadata (completion status, timestamp convention, data source classification, bid/ask prices)
- Service layer orchestrating providers, validator, processor, instrument registry, session calendar
- W1 and MN1 timeframes added
- Comprehensive unit tests (68 Phase 2 tests)
- Demonstration script (`src/market_data/demo.py`)

## Phase 3 — MT5 Integration, PU Prime Demo Connectivity (DONE)

- `MT5BrokerAdapter` behind `BrokerAdapter` (read-only, demo-only)
- Connection management: terminal discovery, configurable executable path
  (`MT5_TERMINAL_PATH`), init/shutdown, status, reconnection, last-error reporting
- Demo-only safety lock: `account_info().trade_mode` verified before any data
  retrieval; live accounts rejected (`MT5LiveAccountError`); no account switching,
  no live login, no order placement/modification
- Dynamic broker symbol discovery + canonical ↔ broker mapping (no ambiguous
  auto-selection; readable discovery report)
- Read-only current market quotes (bid/ask/last/timestamp/spread)
- Historical OHLC candles (M1–D1, W1, MN1) with explicit completed-candle-only
  mode (starts at MT5 position 1; forming candles never classified as complete)
- Optional read-only historical tick interface
- MT5 provider integrated with the Phase 2 Market Data Engine (`DataSource.LIVE`)
- Safe diagnostics script (`python -m src.diagnostics.mt5_diagnostics`)
- Mocked unit tests (41 Phase 3 tests); graceful handling when MT5 is not installed
- Total: 122 tests passing (13 Phase 1 + 68 Phase 2 + 41 Phase 3)

## Phase 4 — Technical Indicator Engine (DONE)

- `src/indicators/` package: `Indicator` ABC, `IndicatorParameters`, `IndicatorResult`, `ReadinessStatus`.
- `IndicatorRegistry` (register/get/exists/supported_indicators/parameter_schema/validate_parameters/unregister) and `IndicatorEngine` service (`calculate()` returning rich `IndicatorResult`; `compute()` ABC compatibility).
- Trend: SMA (multi-period), EMA, ADX, Ichimoku Cloud.
- Momentum: RSI (Wilder's), MACD, Stochastic, CCI, Williams %R.
- Volatility: ATR, Bollinger Bands (population std dev).
- Levels: Classic Pivot Points.
- Volume: VWAP.
- Decimal arithmetic throughout; results aligned 1:1 with input candles (`None` during warm-up).
- Completed candles by default; `allow_incomplete` opt-in (no look-ahead); causal Ichimoku spans.
- Warm-up: SMA/EMA period−1, RSI period, ADX 2·period, Ichimoku span_b−1; Readiness: INSUFFICIENT / WARMING_UP / READY.
- Unit tests per indicator against known values; all phases total 197 tests passing.

## Phase 5 — Strategy Engine

- `Strategy` ABC (`on_tick`, `on_candle`, `enabled`).
- `StrategyEngine` (register/enable/disable/dispatch).
- Starter strategies: EMA crossover, RSI mean-reversion, breakout (skeletons,
  clearly marked non-operational until backtested).

## Phase 6 — Risk Management Engine

- `RiskManager` ABC: `validate`, `compute_position_size`,
  `daily_loss_limit_reached`, `max_positions_reached`.
- Position sizing (% equity per trade), stop-loss/take-profit calculation.
- Daily loss limit, max concurrent positions, max exposure per symbol.
- Centralized risk interface used by `TradeExecutionEngine`.

## Phase 7 — News & Economic Calendar Engine

- `NewsEngine` ABC: upcoming events, `is_trading_allowed`,
  `minutes_to_next_high_impact_event`.
- Investigate legitimate economic calendar data sources and their terms of use
  before integrating (no scraping or bypassing access restrictions).
- Configurable trading restrictions around high-impact events (CPI, NFP, rate
  decisions).

## Phase 8 — Backtesting Engine

- `BacktestingEngine.run(symbol, candles)` evaluating strategies on history.
- Performance metrics: win rate, profit factor, drawdown, expectancy.
- No profitability guarantees; backtest results are not predictive.

## Phase 9 — Paper / Demo Trading Engine

- `PaperTradingEngine`: run strategies on live/demo data without real funds.
- Paper order tracking, equity curve, simulated SL/TP hits.

## Phase 10 — Monitoring & Reporting

- `MonitoringEngine`: record trades, errors, performance, system status.
- Logging, dashboards/reports, alerts.
- Performance reporting (equity curve, drawdown, trade log).

## Phase 11 — Live Trading (only after Phases 1–10 validated on demo)

- Unlock `ENABLE_LIVE_TRADING=true` only after extensive demo/paper validation.
- PuPrime live account connection (MT5).
- Real orders placed only with explicit user approval.
- Never promise win rate or guaranteed profitability.
