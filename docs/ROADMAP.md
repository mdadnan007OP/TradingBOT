# Development Roadmap — Forex Trading Bot

Phase 1 (complete): foundation. Phase 2 (complete): Market Data Engine.
Phase 3 (complete): read-only MT5 integration (PU Prime demo connectivity).
Phase 4 (complete): Technical Indicator Engine. Phase 5 (complete): Strategy
Engine. Phase 6 (complete): Advanced Risk Management Engine. Phase 7 (complete):
News & Economic Calendar Engine.
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

## Phase 5 — Strategy Engine (DONE)

- `src/strategies/` package: `Signal`, `SignalDirection`, `SignalStatus`,
  `MarketRegime`, `Strategy` ABC, `StrategyResult`.
- `StrategyRegistry` (register/get/exists/enable/disable/list/parameters).
- `StrategyManager` (fault-isolated execution, conflict detection, aggregation).
- `SignalService` (indicator→strategy bridge, market regime detection).
- `SignalGenerator` (multi-indicator confirmation engine).
- `SignalConflictResolver` (conflict detection + configurable aggregation
  policies: report_conflicts, consensus, majority, unanimous).
- `MarketRegimeDetector` (TRENDING, RANGING, HIGH_VOLATILITY, LOW_VOLATILITY,
  TRANSITIONING, UNKNOWN using ADX/ATR/moving averages).
- Strategies: TrendFollowing (EMA/SMA/ADX/MACD/RSI), PriceAction (engulfing,
  pin bars, BOS, CHoCH), LiquidityHunting (equal highs/lows, sweeps),
  Trendline (swing pivots, touches, breakouts, retests),
  DailyHighLow (prev day/week high/low breakouts/rejections).
- Profiles: ScalpingProfile (M1/M5/M15), IntradayProfile (M5/M15/M30/H1),
  SwingProfile (H1/H4/D1/W1).
- Signal lifecycle management: unique signal IDs, expiration timestamps,
  technical invalidation levels, duplicate signal prevention, config fingerprints
  for parameter reproducibility.
- Signal quality validation: candle count, OHLC validity, completeness,
  data freshness, indicator readiness checks with explicit rejection categories.
- Risk interface export: `RiskInterfaceSignal` for Phase 6 integration.
- Quality audit: signal lifecycle verification, conflict-resolution verification,
  risk integration interface, look-ahead prevention verified.
- Total: 335 tests passing (13 Phase 1 + 68 Phase 2 + 41 Phase 3 + 75 Phase 4 + 138 Phase 5).

## Phase 6 — Advanced Risk Management Engine (DONE)

- `src/risk_management/` package: centralized, execution-independent risk engine.
- `RiskEngine` service implementing the full evaluation pipeline:
  signal validation → account & instrument info → stop-loss validation →
  position sizing → take-profit validation → portfolio exposure → daily loss
  & drawdown → margin & spread → central risk decision → risk report.
- `RiskDecision` with standardized statuses: `RISK_APPROVED`,
  `RISK_REJECTED`, `REQUIRES_INFORMATION`, `RISK_LOCKED`,
  `CALCULATION_UNAVAILABLE`. Approval is hypothetical only — never authorizes
  execution.
- Instrument-aware position sizing (Decimal arithmetic; volume rounded DOWN to
  lot step; never rounded up beyond risk budget; rejects below broker min lot;
  never guesses missing tick values / contract specs / conversion rates).
- Forex, precious metals, energy, indices support with broker volume min/max/
  step and account-currency conversion.
- Stop-loss validation: LONG below entry / SHORT above entry, positive distance,
  min/max distance limits, technical-invalidation / ATR / swing / fixed methods.
- Take-profit validation: reward-to-risk, ATR-based, technical targets; minimum
  R:R enforced.
- Daily loss protection (starting reference, realized/unrealized PnL, deposits/
  withdrawals excluded from PnL, configurable limit, lockout).
- Drawdown tracking with persisted equity/balance high-watermarks (survives
  restart; cannot be accidentally reset).
- Portfolio exposure: max positions, portfolio risk, per-instrument and
  per-asset-class limits, directional exposure.
- Correlation-aware exposure (Pearson correlation, configurable window/threshold,
  insufficient-data safe handling).
- Margin validation (required vs free margin, margin-usage limits, leverage).
- Circuit breakers with audit history, trigger timestamps, lockout-until, and
  explicit authorized reset (not auto-cleared on restart).
- Deterministic test configurations; all calculations independently unit-tested
  against hand-computed reference values.
- Completely separate from order execution: no `place_order`/`close_order`/
  `order_send`/`order_check` calls; read-only account & position data only.
- Total: 420 tests passing (13 Phase 1 + 68 Phase 2 + 41 Phase 3 + 75 Phase 4 +
  138 Phase 5 + 85 Phase 6).

## Phase 7 — News & Economic Calendar Engine (DONE)

- `src/news/` package: provider-independent economic-calendar & news engine.
  Collects, normalizes and evaluates events, then communicates event-related
  restrictions to the Phase 6 Risk Management Engine. Read-only: never places,
  modifies or closes orders; never executes trades.
- Base contracts (`base.py`): `CalendarProvider`, `NewsProvider`, `NewsEngineABC`.
  Enums: `Importance`, `EventStatus`, `NewsWindowStatus`, `EventCategory`,
  `UnavailablePolicy`.
- Models (`models.py`): immutable `EconomicEvent`, `NewsArticle`,
  `ImpactAssessment`, `NewsRiskContext` (with `blocks_new_entries` /
  `is_caution` / `to_dict`). Timestamps timezone-aware UTC; unresolved times
  flagged, never fabricated.
- Configuration (`config.py`): configurable `NewsConfig` with per-importance
  pre/post windows, per-category overrides, caution threshold, stale timeout,
  unavailable policy, leakage-prevention, and currency/instrument relevance
  rules (Forex, metals, energy, indices, crypto). Conservative degradation.
- Categorization (`registry.py`): configurable keyword→category rules
  (inflation, employment, central bank, growth, commodities). Importance is
  never inferred from the event name.
- Normalization (`normalization.py`): raw provider payloads → `EconomicEvent`;
  missing actual/forecast/previous values stay `None`.
- Calendar (`calendar/`): instrument↔currency mapping (`event_mapping`), impact
  assessment (`impact`), relevant-event scheduler (`scheduler`), revision
  merge + dedup (`revisions`), in-memory event store (`economic_events`).
- Providers (`providers/`):
  - `MockCalendarProvider` / `MockNewsProvider` — deterministic simulated
    events (CPI, NFP, FOMC, rate decisions, EIA, etc.), clearly labeled
    `is_simulated=True`.
  - `CsvCalendarProvider` — local historical CSV with column validation.
  - `MT5CalendarProvider` — reads MQL5-exported JSON/CSV (the MQL5
    `CalendarValueHistory` functions are MQL5-only, not in the Python
    `MetaTrader5` package). Converts **trading-server time → UTC only when a
    verified `server_timezone` is configured**; otherwise marks
    `time_resolved=False` (EVENT_TIME_UNCERTAIN). DST-aware via `tzdata`.
  - `ApiCalendarProvider` / `RssNewsProvider` — interfaces for licensed/permitted
    sources (no network/scraping in tests; credentials via env vars only).
- Filters (`filters/`): relevance (`relevance`), news-window status with
  precedence (EVENT_TIME_UNCERTAIN > NEWS_DATA_UNAVAILABLE > BLOCK_NEW_ENTRIES >
  NEWS_CAUTION > NEWS_CLEAR) handling overlapping events (`news_window`), and
  `build_news_risk_context` (`restriction`).
- Persistence (`persistence/`): `EventRepository` (dedup, revision merge,
  time-range & unresolved queries) and `EventHistory` (revision timeline).
- Service (`service.py`): `NewsService` orchestrates providers → repository →
  `risk_context(instrument)`. Tracks freshness/staleness; `events_as_of()`
  prevents future-information leakage in historical contexts.
- Risk integration: `RiskEngine.evaluate_signal` gained a backward-compatible
  optional `news_context` parameter. When provided, blocking/uncertain/
  unavailable contexts reject new entries; caution adds a warning. When `None`
  (default) no news gate applies (all prior behavior unchanged).
- Dependencies: `tzdata` (Windows) for IANA timezone data (MQL5 server-tz→UTC).
- Total: 499 tests passing (13 Phase 1 + 68 Phase 2 + 41 Phase 3 + 75 Phase 4 +
  138 Phase 5 + 85 Phase 6 + 79 Phase 7).

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
