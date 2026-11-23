# Forex Trading Bot — Phase 1, 2, 3, 4, 5, 6, 7 & 8

Professional, modular foundation for an automated Forex trading system intended
to connect to MetaTrader 5 (MT5) and the PuPrime broker account. Phase 1
establishes structure, configuration, data models, a mock broker adapter, and
engine interfaces. Phase 2 adds a modular Market Data Engine with simulated
and historical CSV data providers. Phase 3 adds a **read-only** MT5 integration
for PU Prime **demo** connectivity (broker quotes and historical candles fed
into the Phase 2 Market Data Engine). Phase 4 adds a **Technical Indicator
Engine** (trend, momentum, volatility, volume, levels). Phase 5 adds a
**Multi-Strategy Engine** that generates standardized trading signals
(LONG / SHORT / NONE) from multiple independent strategies. Phase 6 adds an
**Advanced Risk Management Engine** that validates every proposed trade signal,
calculates risk-adjusted position volume, enforces account- and portfolio-level
protections, and produces explainable risk decisions. Phase 7 adds a **News &
Economic Calendar Engine** that collects, normalizes and evaluates economic
events (CPI, NFP, FOMC, rate decisions, etc.) and communicates event-related
restrictions to the risk engine via an optional, backward-compatible news
context. Phase 8 adds a **Historical Backtesting & Strategy Validation Engine**:
a deterministic, event-driven simulator that replays historical OHLC data through
the Phase 1–7 components (indicators, strategies, risk, news) with realistic
execution, transaction costs, performance analysis, and walk-forward /
optimization / stress validation. **No real orders are placed and live trading is
disabled.**

> **Disclaimer:** This software is for educational and development purposes. It
> does not guarantee profits, and automated trading carries substantial risk of
> loss. Never trade capital you cannot afford to lose.

## Environment

- **OS:** Windows
- **Python:** 3.13.15 (project requires >=3.10)
- **pip:** 26.2.1
- **Git:** 2.55.0
- **IDE:** Google Antigravity (recommended)
- **Trading platform (target):** MetaTrader 5 Desktop Terminal
- **Intended broker:** PU Prime (DEMO account only)

Phase 1, Phase 2, and all unit tests use only the Python standard library (plus
`pytest`). The MT5 integration is **optional**: the project still runs and
passes all tests without the MetaTrader5 package or a running terminal.

## Project structure

```
forex-trading-bot/
├── .env.example            # Copy to .env and fill in your values (never commit .env)
├ .gitignore
├ pyproject.toml            # Package metadata
├ README.md                 # This file
├ docs/
│   ├── ARCHITECTURE.md     # Module communication & design
│   ├── ROADMAP.md          # Phase-by-phase development plan
│   └── RISK_AND_SAFETY.md  # Safety rules & fail-safes
├ src/                      # Application source (package)
│   ├── __init__.py
│   ├── __main__.py         # Allows `python -m src`
│   ├── config.py           # Centralized configuration + env loading
│   ├── logging_config.py   # Logging setup (console + rotating file)
│   ├── models.py           # Data models (tick, candle, order, position, account)
│   ├── engines.py          # Abstract interfaces for all engine modules
│   ├── execution.py        # Trade execution engine (Phase 1 skeleton)
│   ├── main.py             # Application entry point
│   ├── broker/             # Phase 1/3: Broker integration package
│   │   ├── __init__.py     # Exports BrokerAdapter, MockBrokerAdapter (+MT5 lazily)
│   │   ├── base.py         # BrokerAdapter interface + MockBrokerAdapter
│   │   └── mt5/            # Phase 3: MT5 adapter (read-only, demo-only)
│   │       ├── __init__.py
│   │       ├── mt5_adapter.py       # BrokerAdapter implementation
│   │       ├── connection.py        # Terminal discovery, init/shutdown, status
│   │       ├── symbol_discovery.py  # Dynamic symbol discovery + canonical mapping
│   │       ├── market_data.py       # Read-only quotes & historical candles/ticks
│   │       └── exceptions.py        # MT5-specific exceptions
│   ├── diagnostics/        # Phase 3: Diagnostics
│   │   ├── __init__.py
│   │   └── mt5_diagnostics.py       # Read-only connection diagnostic script
│   ├── indicators/         # Phase 4: Technical Indicator Engine
│   │   ├── __init__.py, base.py, registry.py, calculator.py, service.py
│   │   ├── trend/          # SMA, EMA, ADX, Ichimoku Cloud
│   │   ├── momentum/       # RSI, MACD, Stochastic, CCI, Williams %R
│   │   ├── volatility/     # ATR, Bollinger Bands
│   │   └── levels/         # Classic Pivot Points
│   │   └── volume/         # VWAP
│   ├── strategies/         # Phase 5: Multi-Strategy Engine
│   └── risk_management/    # Phase 6: Advanced Risk Management Engine
│       ├── __init__.py, base.py, models.py, config.py, service.py
│       ├── validator.py, position_sizing.py, stop_loss.py, take_profit.py
│       ├── exposure.py, portfolio_risk.py, drawdown.py, correlation.py
│       ├── margin.py, circuit_breaker.py, risk_report.py, persistence.py
│   ├── news/               # Phase 7: News & Economic Calendar Engine
│   │   ├── __init__.py, base.py, models.py, config.py, registry.py
│   │   ├── normalization.py, service.py
│   │   ├── calendar/       # event_mapping, impact, scheduler, revisions, economic_events
│   │   ├── providers/      # mock, csv, mt5_calendar, api, rss
│   │   ├── filters/        # relevance, news_window, restriction
│   │   ├── persistence/    # repository, event_history
│   │   └── risk_integration/  # news_risk_context adapter
│   ├── backtesting/        # Phase 8: Historical Backtesting Engine
│   │   ├── __init__.py, base.py, models.py, config.py
│   │   ├── engine.py       # BacktestEngine orchestrator + create_engine()
│   │   ├── market_simulator.py   # EventScheduler, Bar/BarWindow, chronological reveal
│   │   ├── data_loader.py        # BacktestDataLoader (validate, no look-ahead)
│   │   ├── execution_simulator.py, order_simulator.py
│   │   ├── position_simulator.py, portfolio_simulator.py
│   │   ├── cost_model.py, spread_model.py, slippage_model.py,
│   │   │   commission_model.py, swap_model.py, currency_conversion.py
│   │   ├── performance.py, metrics.py, trade_analyzer.py, drawdown_analysis.py
│   │   ├── strategy_comparison.py, walk_forward.py, optimization.py, stress.py
│   │   ├── reporting.py, persistence.py, demo.py
│   └── market_data/        # Phase 2/3: Market Data Engine
│       ├── __init__.py
│       ├── base.py         # MarketDataProvider ABC
│       ├── models.py       # MarketSymbol, MarketTimeframe, OHLCBar, MarketQuote, DataQualityReport, InstrumentSpec, MarketSession
│       ├── mock_provider.py   # Simulated OHLC generator (seed-based, reproducible)
│       ├── csv_provider.py    # Historical CSV data loader
│       ├── mt5_provider.py    # Phase 3: MT5 provider for the Market Data Engine
│       ├── validator.py       # Data validation engine (session-aware)
│       ├── processor.py       # Data processing engine (sort, filter, gap detection)
│       ├── service.py         # Service layer orchestrating providers
│       ├── sessions.py        # Market session calendars
│       └── demo.py            # Demonstration script
├ tests/                    # Unit tests
│   ├── test_foundation.py   # Phase 1 tests
│   ├── market_data/
│   │   └── test_market_data.py  # Phase 2 tests
│   ├── broker/
│   │   └── test_mt5_adapter.py  # Phase 3 tests (mocked MT5)
│   ├── indicators/          # Phase 4 tests
│   ├── strategies/          # Phase 5 tests
│   ├── risk_management/     # Phase 6 tests
│   │   ├── conftest.py
│   │   ├── test_position_sizing.py
│   │   ├── test_stop_loss_take_profit.py
│   │   ├── test_daily_drawdown.py
│   │   ├── test_portfolio_margin_cb.py
│   │   ├── test_validator.py
│   │   ├── test_service.py
│   │   └── test_risk_report.py
│   └── news/                # Phase 7 tests
│       ├── conftest.py
│       ├── test_models.py, test_normalization.py, test_providers.py
│       ├── test_calendar.py, test_filters.py, test_persistence.py
│       ├── test_service.py, test_risk_integration.py
│   └── backtesting/         # Phase 8 tests
│       ├── conftest.py
│       ├── test_engine.py, test_engine_advanced.py, test_engine_risk_state.py
│       ├── test_costs.py, test_execution.py, test_portfolio.py
│       ├── test_data_loader.py, test_performance.py
│       ├── test_walk_forward.py, test_optimization.py, test_stress.py
│       └── test_reporting.py
└ docs/
    ├── ARCHITECTURE.md     # Module communication & design
    ├── ROADMAP.md          # Phase-by-phase development plan
    └── RISK_AND_SAFETY.md  # Safety rules & fail-safes
```

## Setup

1. Open the project folder in your IDE (Google Antigravity or any Python IDE).
2. (Optional but recommended) Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. Copy the example environment file:

   ```powershell
   copy .env.example .env
   ```

   Edit `.env` if you want to override defaults (e.g. `LOG_LEVEL=DEBUG`).
   **Never store broker passwords or API keys in `.env`.**

4. (Optional — only for MT5 live demo connectivity) Install the MT5 package:

   ```powershell
   pip install MetaTrader5
   ```

   Or install the optional dependency group:

   ```powershell
   pip install -e ".[mt5]"
   ```

## Run the application

From the project root:

```powershell
python -m src.main
```

Expected output (console + `logs/trading_bot.log`):

```
INFO | Forex Trading Bot starting (Phase 1 foundation)
INFO | Trading mode: simulation | Live locked: True
INFO | Mock broker connected: True
INFO | Trade execution engine ready
INFO | Demo order request (not submitted): BUY XAUUSD market @ 0.01 lots
INFO | Account: 123456 | balance=10000.0 USD | trade_allowed=True
INFO | Available instruments: 5
INFO | Forex Trading Bot stopped
```

The bot runs in **simulation mode** using the mock broker and exits cleanly.

## Run the Market Data Engine demo

From the project root:

```powershell
python -m src.market_data.demo
```

This demonstrates:
1. Simulated OHLC candle generation (mock provider, seed-based, reproducible)
2. Historical CSV data loading
3. Data validation and quality reporting
4. Data processing (sort, filter, gap detection)
5. Service layer orchestration

## MT5 integration (Phase 3 — read-only, demo-only)

### Prerequisites

1. **MetaTrader 5 Desktop Terminal** must be installed on Windows.
2. Open the terminal and **manually log into your PU Prime DEMO account**.
   Leave the terminal running and logged in.
3. Install the Python package: `pip install MetaTrader5`.

The Python application **never** handles your password — it connects to the
already-authenticated desktop terminal.

### Configure the terminal path (optional)

If auto-discovery cannot find the terminal, set the executable path either via
environment variable (in `.env`):

```
MT5_TERMINAL_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
```

or pass it explicitly on the command line (see diagnostics below).

### Discover the assigned PU Prime server

After logging into the terminal manually, run the diagnostics — the assigned
server name is reported (e.g. `PUPrime-Demo`). If the terminal auto-connects
to the correct demo server, no further configuration is needed.

### Run connection diagnostics

```powershell
python -m src.diagnostics.mt5_diagnostics
python -m src.diagnostics.mt5_diagnostics --terminal "C:\Program Files\MetaTrader 5\terminal64.exe"
python -m src.diagnostics.mt5_diagnostics --symbol EURUSD
python -m src.diagnostics.mt5_diagnostics --json
```

The diagnostic reports: Python version, MT5 package version, terminal
connection status, terminal version/build, account mode (DEMO, or rejected
LIVE), server name (safe summary only), discovered instrument count, the full
symbol discovery report, selected symbol metadata, current quote, and
historical candle retrieval status. It **never** prints passwords, login
numbers, balances, or personal account information, and it **fails safely**
when the terminal is unavailable.

### MT5 IPC troubleshooting (-10005 IPC timeout)

If `mt5.initialize()` fails with `(-10005, 'IPC timeout')` or similar:

1. **Use the correct terminal executable.** Two installations were found on
   this machine:
   - `C:\Program Files\PU Prime MT5 Terminal\terminal64.exe` (PU Prime)
   - `C:\Program Files\MetaTrader 5\terminal64.exe` (generic MetaQuotes)
   Configure `MT5_TERMINAL_PATH` to point at the PU Prime terminal:
   ```
   MT5_TERMINAL_PATH=C:\Program Files\PU Prime MT5 Terminal\terminal64.exe
   ```

2. **The terminal must be running AND logged in before Python connects.**
   Open MetaTrader 5, manually log into your PU Prime DEMO account, and keep
   the terminal running. The adapter does not store or handle your password.

3. **Only one terminal instance should run.** Multiple terminal processes can
   cause IPC port conflicts (port 22346).

4. **Python and terminal elevation must match.** Both should run at the same
   privilege level (both unelevated, or both elevated).

5. **Use the independent diagnostic for isolation:**
   ```
   python tools/mt5_connection_repair.py --terminal "C:\Program Files\PU Prime MT5 Terminal\terminal64.exe"
   ```

### Use MT5 data in the Market Data Engine

```python
from src.broker.mt5 import MT5BrokerAdapter
from src.market_data.mt5_provider import MT5MarketDataProvider
from src.market_data.service import MarketDataService
from src.market_data.models import MarketTimeframe

adapter = MT5BrokerAdapter(canonical_symbols=["XAUUSD", "EURUSD"])
service = MarketDataService()

provider = MT5MarketDataProvider(adapter)
service.register_provider("mt5", provider)

# Latest completed H1 candles (broker-provided, read-only)
bars = service.get_candles(
    "XAUUSD", MarketTimeframe.H1,
    start_time=..., end_time=...,
)
quote = service.get_quote("XAUUSD")
service.disconnect_all()
```

Every record returned by the MT5 provider flows through the existing Phase 2
validation and processing (`DataSource.LIVE`) and is never mislabeled as
simulated or historical CSV data.

### Run automated tests

```powershell
python -m pytest tests/ -v
```

MT5 unit tests use a mocked MT5 interface — no terminal or account is
required. Terminal-dependent real-connection testing is performed manually via
the diagnostics script.

## Safety (mandatory)

- Live trading is **disabled by default** (`ENABLE_LIVE_TRADING=false`, `TRADING_MODE=simulation`).
- No real orders are placed in any phase.
- The MT5 adapter is **read-only**: `place_order` and `close_order` are
  hard-disabled (rejected with error 403); `get_orders` / `get_positions`
  perform genuine read-only retrieval via `orders_get()` / `positions_get()`;
  `order_send` / `order_check` are never called. The timeframe-less
  `BrokerAdapter.get_candles` bridge fails explicitly to avoid mislabeled data.
- The MT5 adapter accepts **demo accounts only** (official `trade_mode`
  enumeration: demo accepted; contest and real rejected; missing account info
  fails safely); it rejects before any market data is retrieved. It never
  switches accounts, never attempts live login, and never enables live trading.
- No broker credentials are requested or stored; the manually authenticated
  desktop terminal is reused.
- Passwords, login numbers, balances, and personal account data are never
  printed or logged.
- The mock broker and mock market data provider are used for all automated
  testing.
- No fabricated real market data — simulated prices are explicitly labeled.

See `docs/RISK_AND_SAFETY.md` for the full safety policy.

## What is implemented

### Phase 1 — Foundation
- Project folder structure
- Centralized config management with `.env` support
- Data models (Instrument, Tick, Candle, Order, Position, AccountInfo, etc.)
- Logging system (console + rotating file)
- Broker adapter interface + MockBrokerAdapter
- Trade execution engine with live-trade lock
- Abstract interfaces for all 10 engine modules
- Application entry point (`src/main.py`)
- Unit tests
- Documentation (README, architecture, roadmap, risk & safety)

### Phase 2 — Market Data Engine
- Universal instrument registry with multi-asset classes (Forex, metals, energy, indices, equities, crypto, other)
- Configurable instrument specifications (broker symbol mapping, price precision, tick/pip size, contract size, volume type, supported timeframes, market session)
- Provider interface: `MarketDataProvider` ABC
- Mock market data provider (simulated OHLC, seed-based, reproducible, clearly labeled `is_simulated=True`)
- Historical CSV provider (local file loading, column validation, optional volumes/spread/bid/ask)
- Data validation engine (session-aware: distinguishes expected market closures from unexpected gaps)
- Market session calendars (Forex weekend, crypto 24/7, equity daily hours, configurable sessions)
- Data processing engine (sort, deduplicate, filter by symbol/timeframe/date-range, missing interval detection)
- Candle quality metadata (completion status, timestamp convention, data source classification, bid/ask prices)
- Service layer orchestrating providers, validator, processor, instrument registry, session calendar
- W1 and MN1 timeframes added
- Comprehensive unit tests (68 Phase 2 tests)
- Demonstration script (`src/market_data/demo.py`)

### Phase 3 — MT5 Integration (read-only, demo-only)
- MT5 connection management (terminal discovery, configurable executable path, init/shutdown, status, reconnection, last-error reporting)
- Demo-only safety lock (account `trade_mode` checked before any data retrieval; live accounts rejected)
- Dynamic broker symbol discovery + canonical ↔ broker symbol mapping (no ambiguous auto-selection)
- Read-only current market quotes (bid/ask/last/timestamp/spread)
- Historical OHLC candle retrieval for M1–D1, W1, MN1 with explicit completed-candle-only mode (starts at MT5 position 1)
- Optional historical tick retrieval interface
- MT5 provider integrated with the Phase 2 Market Data Engine (`DataSource.LIVE`)
- Safe connection diagnostics script (`python -m src.diagnostics.mt5_diagnostics`)
- Mocked unit tests (41 Phase 3 tests) with graceful handling when MT5 is not installed
- Total: 499 tests passing (13 Phase 1 + 68 Phase 2 + 41 Phase 3 + 75 Phase 4 + 138 Phase 5 + 85 Phase 6 + 79 Phase 7).

### Phase 4 — Technical Indicator Engine
- `src/indicators/` package: `Indicator` ABC, `IndicatorParameters`, `IndicatorResult`, `ReadinessStatus`.
- `IndicatorRegistry` (register/get/exists/supported_indicators/parameter_schema/validate_parameters/unregister) and `IndicatorEngine` service (`calculate()` returning rich `IndicatorResult`; `compute()` ABC compatibility).
- Trend: SMA (multi-period), EMA, ADX, Ichimoku Cloud.
- Momentum: RSI (Wilder's), MACD, Stochastic, CCI, Williams %R.
- Volatility: ATR, Bollinger Bands (population std dev).
- Levels: Classic Pivot Points.
- Volume: VWAP.
- Decimal arithmetic throughout; results aligned 1:1 with input candles (`None` during warm-up).
- Completed candles by default; `allow_incomplete` opt-in (no look-ahead); causal Ichimoku spans.
- Readiness: INSUFFICIENT / WARMING_UP / READY.
- Comprehensive unit tests per indicator against known values.

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
- Standardized `Signal` model with full provenance (signal ID, strategy name,
  instrument, direction, timestamps, reference price, technical invalidation,
  indicator snapshot, market regime, confirmation conditions, explanation).
- Decimal arithmetic throughout; no order execution; no look-ahead bias.
- Fault isolation: one failed strategy does not crash the system.
- Signal lifecycle management: unique signal IDs, expiration timestamps,
  technical invalidation levels, duplicate signal prevention, config fingerprints
  for parameter reproducibility.
- Signal quality validation: candle count, OHLC validity, completeness,
  data freshness, indicator readiness checks with explicit rejection categories.
- Risk interface export: `RiskInterfaceSignal` for Phase 6 integration.
- Comprehensive quality audit tests: duplicate signals, expiration, invalidation,
  versioning, explainability, stale data, invalid indicators, risk interface,
  look-ahead prevention.

### Phase 6 — Advanced Risk Management Engine (DONE)

- `src/risk_management/` package: centralized, execution-independent risk engine.
- `RiskEngine` service implementing the full evaluation pipeline:
  signal validation → account & instrument info → stop-loss validation →
  position sizing → take-profit validation → portfolio exposure → daily loss
  & drawdown → margin & spread → central risk decision → risk report.
- `RiskDecision` with standardized statuses:
  `RISK_APPROVED`, `RISK_REJECTED`, `REQUIRES_INFORMATION`, `RISK_LOCKED`,
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

### Phase 7 — News & Economic Calendar Engine (DONE)

- `src/news/` package: provider-independent economic-calendar & news engine.
- Base contracts (`CalendarProvider`, `NewsProvider`, `NewsEngineABC`) and enums
  (`Importance`, `EventStatus`, `NewsWindowStatus`, `EventCategory`,
  `UnavailablePolicy`).
- Immutable models: `EconomicEvent`, `NewsArticle`, `ImpactAssessment`,
  `NewsRiskContext` (UTC timestamps; unresolved-time flagged, never fabricated).
- Configurable `NewsConfig` with per-importance pre/post windows, per-category
  overrides, caution threshold, stale timeout, unavailable policy, and
  currency/instrument relevance rules (Forex, metals, energy, indices, crypto).
- Categorization registry (inflation, employment, central bank, growth,
  commodities); importance is never inferred from the event name.
- Providers: deterministic mock (simulated CPI/NFP/FOMC/rate/EIA events), CSV
  historical loader, **MQL5-export bridge** (server-tz → UTC only when a
  verified timezone is configured, else EVENT_TIME_UNCERTAIN), and licensed
  API/RSS interfaces (no network/scraping in tests).
- Filters: relevance filtering, consolidated news-window status
  (`EVENT_TIME_UNCERTAIN > NEWS_DATA_UNAVAILABLE > BLOCK_NEW_ENTRIES >
  NEWS_CAUTION > NEWS_CLEAR`) with overlapping-event handling.
- Persistence: `EventRepository` (dedup, revision merge, range/unresolved
  queries) and `EventHistory` (revision timeline).
- `NewsService` orchestrator with freshness/staleness tracking and
  leakage-safe `events_as_of()` for historical contexts.
- Backward-compatible risk integration: `RiskEngine.evaluate_signal(...,
  news_context=None)`. Blocking/uncertain/unavailable contexts reject new
  entries; caution adds a warning; `None` keeps all prior behavior.
- Dependency: `tzdata` (Windows) for IANA timezone data (MQL5 server-tz → UTC).
- Total: 499 tests passing (13 + 68 + 41 + 75 + 138 + 85 + 79 Phase 7).

### Phase 8 — Historical Backtesting & Strategy Validation Engine (DONE)

- `src/backtesting/` package: a deterministic, event-driven simulator that reuses
  Phase 1–7 components unchanged and **never** places real/demo orders (no
  `order_send`/`order_check` calls).
- `BacktestEngine`: per-bar lifecycle — fill pending orders → check exits →
  generate signals via `SignalService` → news gate → `RiskEngine.evaluate_signal`
  (at simulated time) → open position at the next bar. Look-ahead is prevented:
  indicators/strategies see only candles `ts <= now`; entries fill the next bar.
- `MarketSimulator`/`EventScheduler`: strict chronological reveal of `Bar`/
  `BarWindow`, never exposing future candles.
- `BacktestDataLoader`: validates timestamps, OHLC integrity and duplicates;
  preserves missing data (no fabricated fills); labels invalid/incomplete bars
  as `DataSource.SIMULATED`.
- Execution & cost realism: `SpreadModel`, `SlippageModel` (adverse only),
  `CommissionModel` (none/per-lot/fixed), `SwapModel` (overnight), and
  `CurrencyConversion` (as-of rates, never future). LONG fills at ask, SHORT at
  bid; ambiguous SL/TP resolved by a conservative default (stop-first), flagged.
- `OrderSimulator`, `PositionSimulator`, `PortfolioSimulator`: pending → filled →
  open → closed lifecycle; gross/net PnL, R-multiple; hedging + simplified
  netting; equity/balance tracking; rejected-signal and risk-lockout logs.
- Performance analysis: `PerformanceAnalyzer`, `Metrics` (Sharpe/Sortino
  annualized by the median bar interval; warns when < 30 trades),
  `TradeAnalyzer`, `DrawdownAnalysis` (max/avg drawdown, recovery), and
  `StrategyComparison` across strategy subsets.
- Validation: `WalkForward` (in-sample / out-of-sample split), `Optimization`
  (`grid_search` + `robustness_score`/`best_candidate`), and `Stress` (spread
  2×/5×, adverse slippage, elevated commission).
- Reporting & persistence: `reporting.py` (JSON/CSV reports, monthly
  performance, formatted summary) and `persistence.py` (save/load results).
- Backward-compatible risk integration: `AccountSnapshot.is_stale(reference_time)`,
  `validate_account(reference_time)`, and `RiskEngine.evaluate_signal(now=...)`
  let risk checks run at simulated time instead of wall-clock `datetime.now()`.
- Deterministic synthetic demo: `python -m src.backtesting.demo` (SMA-crossover
  `MomentumStrategy`) writes to the git-ignored `backtest_output/` directory.
- Total: 593 tests passing (13 + 68 + 41 + 75 + 138 + 85 + 79 + 94 Phase 8).

## What remains

See `docs/ROADMAP.md`. Phases 1–8 are complete; subsequent phases cover
paper/demo trading (9), monitoring/reporting (10), and live trading (11, only
after extensive demo/paper validation).


## Known limitations (Phase 3)

- Real broker connection has **not** been tested yet — diagnostics must be run
  on your machine with the PU Prime demo terminal open and logged in.
- Broker-specific symbol names, contract sizes, and available instruments can
  only be confirmed against the live demo server (auto-discovery + mapping
  report).
- Historical tick retrieval is an optional interface only (no continuous
  streaming).
- The Phase 1 `BrokerAdapter.get_candles` bridge uses a simplified conversion;
  use the Phase 2 `MarketDataService`/`MT5MarketDataProvider` for full OHLC
  fidelity (tick/real volume, spread, source provenance).

## License

MIT
