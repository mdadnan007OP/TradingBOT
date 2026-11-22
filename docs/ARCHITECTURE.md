# Architecture — Forex Trading Bot (Phases 1, 2 & 3)

This document explains how the modules communicate and the design rationale
behind the Phase 1 foundation, Phase 2 Market Data Engine, and the Phase 3
read-only MT5 integration.

## Design principles

1. **Separation of concerns** — each module has one responsibility.
2. **Interface-driven** — engines depend on ABCs, not concrete implementations.
3. **Broker-agnostic core** — business models know nothing about MT5 or PuPrime.
4. **Fail-safe by default** — missing data, connection failure, and unexpected
   errors degrade gracefully; live trading stays locked.
5. **No secrets** — credentials are never stored or logged.
6. **Demo-only safety** — broker connections accept demo accounts only.

## Module overview

### Phase 1 — Foundation

| Module | File | Responsibility |
|--------|------|----------------|
| Configuration | `src/config.py` | Centralized config + `.env` loading; trading-mode & safety flags |
| Logging | `src/logging_config.py` | Console + rotating-file logging |
| Data models | `src/models.py` | Instrument, Tick, Candle, Order, Position, AccountInfo, TradeResultModel |
| Broker integration | `src/broker/` | `BrokerAdapter` ABC + `MockBrokerAdapter` (in `base.py`) |
| Engine interfaces | `src/engines.py` | Abstract interfaces for all 10 engine modules |
| Trade execution | `src/execution.py` | Routes orders through risk + broker with live-trade lock |
| Entry point | `src/main.py` | Wires config, logging, mock broker, execution engine |

### Phase 2 — Market Data Engine

| Module | File | Responsibility |
|--------|------|----------------|
| Market data models | `src/market_data/models.py` | `MarketSymbol`, `MarketTimeframe`, `OHLCBar`, `MarketQuote`, `DataQualityReport`, `InstrumentSpec`, `MarketSession`, `DataSource`, `VolumeType`, `CandleCompletion` |
| Provider interface | `src/market_data/base.py` | `MarketDataProvider` ABC — provider contract |
| Mock provider | `src/market_data/mock_provider.py` | Simulated OHLC generator (seed-based, reproducible, `is_simulated=True`) |
| CSV provider | `src/market_data/csv_provider.py` | Local CSV historical data loader |
| Sessions | `src/market_data/sessions.py` | `SessionCalendar`, `MarketSession` — market session awareness |
| Validator | `src/market_data/validator.py` | Session-aware price/OHLC/timestamp validation + quality reports |
| Processor | `src/market_data/processor.py` | Sort, deduplicate, filter, gap detection |
| Service | `src/market_data/service.py` | Orchestrates providers, validator, processor, instrument registry, session calendar |
| Demo | `src/market_data/demo.py` | Demonstration script |

### Phase 3 — MT5 Integration (read-only, demo-only)

| Module | File | Responsibility |
|--------|------|----------------|
| MT5 adapter | `src/broker/mt5/mt5_adapter.py` | `BrokerAdapter` implementation (read-only; order placement/closing hard-disabled; read-only `orders_get()`/`positions_get()` retrieval; timeframe-less `get_candles` bridge fails explicitly) |
| Connection | `src/broker/mt5/connection.py` | Terminal discovery, init/shutdown, status, reconnection, last-error reporting |
| Symbol discovery | `src/broker/mt5/symbol_discovery.py` | Dynamic broker symbol discovery + canonical ↔ broker mapping |
| Market data | `src/broker/mt5/market_data.py` | Read-only quotes, historical OHLC candles, optional historical ticks |
| Exceptions | `src/broker/mt5/exceptions.py` | MT5-specific exception hierarchy |
| MT5 provider | `src/market_data/mt5_provider.py` | `MarketDataProvider` implementation for the Phase 2 engine |
| Diagnostics | `src/diagnostics/mt5_diagnostics.py` | Safe connection diagnostic script |

## Data flow (Phase 1)

```
main.py
  └─ setup_logging()
  ├─ load CONFIG (from .env + environment)
  ├─ MockBrokerAdapter.connect()
  ├─ TradeExecutionEngineImpl(broker, risk_manager=None)
  ├─ build demo OrderRequest   (NOT submitted)
  ├─ broker.get_account_info()
  ├─ broker.get_instruments()
  └─ MockBrokerAdapter.disconnect()
```

## Data flow (Phase 2 — Market Data Engine)

```
MarketDataService
  ├─ register_provider(MockMarketDataProvider | HistoricalCSVProvider | MT5MarketDataProvider)
  ├─ provider.get_candles(symbol, timeframe, start, end) -> List[OHLCBar]
  ├─ DataProcessor.standardize(bars)        # sort, deduplicate
  ├─ DataValidator.validate_bars(...)       # quality report
  └─ return validated, standardized bars
```

## Data flow (Phase 3 — MT5 read-only integration)

```
MT5BrokerAdapter.connect()
  ├─ MT5ConnectionManager.initialize()           # discover terminal, mt5.initialize()
  ├─ MT5AccountInfo.is_demo_account()            # DEMO-ONLY SAFETY LOCK (trade_mode == 0)
  ├─ MT5SymbolDiscovery.discover_symbols()       # dynamic symbol list
  ├─ MT5SymbolDiscovery.auto_map_symbols()       # canonical -> broker mapping
  └─ MT5MarketData(connection, symbol_mapping)   # read-only data access

MT5MarketDataProvider(adapter)                    # implements MarketDataProvider
  └─ MarketDataService.register_provider("mt5", provider)
       └─ get_candles/get_latest_candle/get_quote -> OHLCBar/MarketQuote (DataSource.LIVE)
```

Future flow (Phase 4+):

```
MarketDataEngine -> IndicatorEngine -> StrategyEngine -> RiskManager ->
TradeExecutionEngine -> BrokerAdapter -> (MT5 or Mock)
```

## Phase 4 — Technical Indicator Engine

| Module | File | Responsibility |
|--------|------|----------------|
| Indicator base | `src/indicators/base.py` | `Indicator` ABC, `IndicatorParameters`, `IndicatorResult`, `ReadinessStatus` |
| Registry | `src/indicators/registry.py` | `IndicatorRegistry` — register/get/exists/supported_indicators/parameter_schema/validate_parameters/unregister |
| Calculator | `src/indicators/calculator.py` | Shared math: SMA, EMA, Wilder smoothing, typical price, mean deviation, true range, std dev, rolling sum |
| Service | `src/indicators/service.py` | `IndicatorEngine` — `calculate()` returning rich `IndicatorResult`; `compute()` ABC compatibility |
| Trend | `src/indicators/trend/{sma,ema,adx,ichimoku}.py` | SMA, EMA, ADX, Ichimoku Cloud |
| Momentum | `src/indicators/momentum/{rsi,macd,stochastic,cci,williams_r}.py` | RSI (Wilder's), MACD, Stochastic, CCI, Williams %R |
| Volatility | `src/indicators/volatility/{atr,bollinger_bands}.py` | ATR, Bollinger Bands (population std dev) |
| Levels | `src/indicators/levels/pivot_points.py` | Classic Pivot Points |
| Volume | `src/indicators/volume/vwap.py` | VWAP |

### Design

- **Decimal arithmetic** throughout; no floating-point drift.
- **Results aligned 1:1** with input candles (`None` during warm-up; no look-ahead).
- **Completed candles by default**; `allow_incomplete` opt-in.
- **Readiness**: `INSUFFICIENT` → `WARMING_UP` → `READY` as data accumulates.
- **Warm-up**: SMA/EMA `period−1`, RSI `period`, ADX `2·period`, Ichimoku `span_b−1`.
- `compute()` maps `None` values to `float("nan")` for legacy ABC compatibility.

### Inter-module dependencies

- `src/indicators/base.py` — depends on `src/market_data/models.py` only.
- `src/indicators/calculator.py` — depends on `src/market_data/models.py` only.
- `src/indicators/{trend,momentum,volatility,levels,volume}/*.py` — depend on `base.py`, `calculator.py`, `market_data/models.py`.
- `src/indicators/registry.py` — depends on `base.py`.
- `src/indicators/service.py` — depends on `base.py`, `registry.py`, `market_data/models.py`.
- `src/indicators/__init__.py` — wires `create_engine()` factory.

### Connection management (`connection.py`)

- `MT5ConnectionManager` — discovers the terminal executable (env var
  `MT5_TERMINAL_PATH`, standard Program Files paths, or AppData glob),
  initializes/shuts down the MT5 API, checks connection health, and reports
  the last error. Reuses a **manually authenticated** desktop terminal; the
  Python app never handles passwords.
- `MT5AccountInfo` — wraps `account_info()` and exposes only a demo/live
  verdict and a safe summary (mode, server, currency). Never logs the full
  account object, logins, or balances.

### Demo-only safety lock

Before any market data is retrieved, `MT5BrokerAdapter.connect()` checks
`account_info().trade_mode` using the official MT5 enumeration
(`ACCOUNT_TRADE_MODE_DEMO=0`, `ACCOUNT_TRADE_MODE_CONTEST=1`,
`ACCOUNT_TRADE_MODE_REAL=2`). Only `trade_mode == 0` (demo) is accepted.
Missing account information raises `MT5AccountError`; contest and real/live
accounts raise `MT5LiveAccountError`; the adapter shuts the connection down and
**no** market data is returned. The adapter never switches accounts, never
attempts live login (never calls `mt5.login()`), and never enables trading.

### Read-only orders and positions

`get_orders()` and `get_positions()` perform genuine **read-only** retrieval via
`orders_get()` / `positions_get()`, converting MT5 records into the Phase 1
`Order` / `Position` models. They never place, modify, or cancel anything, and
never call `order_send` or `order_check`. An empty list is returned only when
the broker genuinely reports no orders/positions (or the call is unavailable).

### Candle retrieval and the timeframe bridge

`MT5MarketData.get_candles()` uses `copy_rates_range()` with the exact MT5
timeframe constant for the requested `MarketTimeframe` (M1→1, M5→5, M15→15,
M30→30, H1→60, H4→240, D1→1440, W1→10080, MN1→43200) and preserves
open/high/low/close, tick volume, real volume, spread, UTC timestamps, and
completed-candle status. The Phase 1 `BrokerAdapter.get_candles(symbol, count)`
bridge carries no timeframe, so it **fails explicitly** with `MT5DataError`
rather than silently returning mislabeled M1 candles. The authoritative
timeframe-aware path is `MT5MarketDataProvider` used through
`MarketDataService`.

### Symbol discovery and mapping (`symbol_discovery.py`)

- `discover_symbols()` calls `symbols_get()` and captures broker metadata
  (description, currencies, digits, point, tick size/value, contract size,
  min/max/step volume, trade mode, swaps, session volume, spread, margins,
  path).
- `find_broker_symbol(canonical)` matches against a known-variant table plus
  common suffixes (`.cash`, `.raw`, `.ecn`, `.pro`, `m`, `.fx`). Ambiguous
  matches are never auto-selected — the first (highest-confidence) candidate
  is used and the mapping records the candidate count.
- `to_instrument_spec()` converts broker metadata into an `InstrumentSpec`
  (asset class inferred from symbol path/name, volume type from session
  volume, all supported timeframes).
- `generate_discovery_report()` produces a human-readable mapping report.

### Market data (`market_data.py`)

- `get_quote()` — uses `symbol_info_tick()`; returns bid/ask/last/timestamp
  (UTC) as a `MarketQuote`.
- `get_candles()` — uses `copy_rates_range()`; converts MT5 rates to
  `OHLCBar` (UTC timestamps, tick/real volume, spread, `DataSource.LIVE`).
  **Completed-candle handling:** bars are sorted by time; a bar whose period
  end is in the future is treated as forming and skipped when
  `completed_only=True` (never silently classified as complete).
- `get_latest_candle()` — for completed-only retrieval starts at MT5
  **position 1** per MT5 semantics (`copy_rates_from_pos(symbol, tf, 1, 1)`);
  with `completed_only=False` returns the position-0 forming candle marked
  `is_complete=False`.
- `get_historical_ticks()` — optional read-only tick range interface (no
  streaming).

### Integration with the Phase 2 engine (`mt5_provider.py`)

`MT5MarketDataProvider` implements the `MarketDataProvider` ABC. All records
flow through the existing `DataProcessor.standardize()` and
`DataValidator.validate_bars()` in `MarketDataService`, and are tagged
`DataSource.LIVE` — never mislabeled as simulated or historical CSV data.

### Diagnostics (`src/diagnostics/mt5_diagnostics.py`)

Reports environment, MT5 package version, terminal connection status,
terminal version/build, account mode (DEMO or rejected LIVE), safe server
summary, discovered instrument count, full symbol discovery report, selected
symbol metadata, current quote, and candle retrieval status. Fails safely
when the terminal/package is unavailable and never exposes credentials or
account identifiers.

## Inter-module dependencies

### Phase 1

- `config.py` — depends on nothing in `src` (loads env only).
- `logging_config.py` — depends on `config.py`.
- `models.py` — depends on nothing.
- `broker/base.py` — depends on `config.py`, `models.py`.
- `engines.py` — depends on `broker/base.py`, `models.py`.
- `execution.py` — depends on `config.py`, `broker`, `engines.py`, `models.py`.
- `main.py` — depends on `config.py`, `logging_config.py`, `broker`, `engines.py`, `execution.py`, `models.py`.

### Phase 2

- `market_data/models.py` — depends on nothing external.
- `market_data/base.py` — depends on `market_data/models.py`.
- `market_data/sessions.py` — depends on nothing external.
- `market_data/mock_provider.py` — depends on `config.py`, `market_data/base.py`, `market_data/models.py`.
- `market_data/csv_provider.py` — depends on `market_data/base.py`, `market_data/models.py`.
- `market_data/validator.py` — depends on `market_data/models.py`, `market_data/sessions.py`.
- `market_data/processor.py` — depends on `market_data/models.py`.
- `market_data/service.py` — depends on `market_data/base.py`, `market_data/models.py`, `market_data/processor.py`, `market_data/sessions.py`, `market_data/validator.py`.
- `market_data/demo.py` — depends on all market_data modules.

### Phase 3

- `broker/mt5/exceptions.py` — depends on nothing.
- `broker/mt5/connection.py` — depends on `broker/mt5/exceptions.py` (MT5 imported lazily).
- `broker/mt5/symbol_discovery.py` — depends on `market_data/models.py`, `broker/mt5/exceptions.py`.
- `broker/mt5/market_data.py` — depends on `market_data/models.py`, `broker/mt5/connection.py`, `broker/mt5/exceptions.py`.
- `broker/mt5/mt5_adapter.py` — depends on `broker/base.py`, `config.py`, `models.py`, `broker/mt5/*`.
- `market_data/mt5_provider.py` — depends on `market_data/base.py`, `market_data/models.py`, `broker/mt5` (lazy).
- `diagnostics/mt5_diagnostics.py` — depends on `broker/mt5` (lazy import so missing package fails safely).

To avoid circular imports, the MT5 modules are imported lazily:
`src/broker/__init__.py` and `src/market_data/__init__.py` append the MT5
exports inside `try/except ImportError`, so the packages work without the
MetaTrader5 dependency installed.

## Instrument Registry

The `InstrumentSpec` dataclass (in `models.py`) provides configurable metadata for each instrument:

- **canonical_symbol**: Internal canonical symbol (e.g. `XAUUSD`)
- **broker_symbol**: Broker-specific symbol, if different from canonical
- **instrument_type**: Asset class (forex, metal, energy, index, equity, crypto, other)
- **base_currency / quote_currency**: For pairs only
- **price_precision / tick_size / pip_size**: Price granularity (optional, not assumed)
- **contract_size**: Contract size per lot (optional, not assumed)
- **volume_type**: Tick, real, both, or none
- **supported_timeframes**: Timeframes supported for this instrument
- **market_session**: Session identifier (e.g. `forex`, `crypto`, `energy`)

The `DEFAULT_INSTRUMENT_SPECS` list includes 19 instruments across 7 asset classes.
Broker-specific values (contract sizes, pip sizes, etc.) are NOT assumed and remain
`None` until verified in Phase 3 broker integration.

To register a custom instrument::

    service.register_instrument_spec(
        InstrumentSpec(
            canonical_symbol="WTIUSD",
            broker_symbol="WTI",
            name="WTI Crude Oil",
            instrument_type=InstrumentType.ENERGY,
            price_precision=3,
            tick_size=Decimal("0.001"),
            contract_size=Decimal("1000"),
            market_session="energy",
        )
    )

## Market Session Awareness

The `SessionCalendar` (in `sessions.py`) distinguishes expected market closures
from unexpected missing candles:

- **Forex**: Closed Saturday, Sunday before 22:00 UTC, Friday after 22:00 UTC
- **Crypto**: 24/7/365 (always open)
- **Energy/Indices**: CME Globex-style schedule with daily breaks
- **Equity**: Regular trading hours, weekend closed

The validator uses the session calendar to filter out missing intervals that
coincide with expected closures (e.g. Forex weekends are not reported as data
failures).

Session calendars are extensible for broker-specific schedules::

    calendar.register_session("custom", MarketSession(
        session_id="custom",
        description="Custom broker session",
        is_24h=False,
        weekend_days=frozenset({5, 6}),
        daily_open_utc="09:30",
        daily_close_utc="16:00",
    ))

## Candle Quality Metadata

`OHLCBar` now includes optional quality metadata:

- **is_complete**: Whether the bar is complete or incomplete/partial
- **timestamp_convention**: Convention used (e.g. `bar_open`)
- **data_source**: `SIMULATED`, `HISTORICAL`, or `LIVE`
- **bid / ask**: Bid/ask prices at bar time, if available

Incomplete candles cannot be treated as historical (raises `ValueError`).

There are no circular imports.

## Safety boundaries

- `CONFIG.trading.live_locked` is a master kill-switch. `TradeExecutionEngineImpl`
  rejects every `execute()` / `close_position()` call while `live_locked` is true.
- `MockBrokerAdapter` simulates only; it never contacts a real market or broker.
- `MockMarketDataProvider` is explicitly simulated: `is_simulated=True`, all
  prices labeled as simulated. Never presented as genuine market data.
- `HistoricalCSVProvider` reads local files only; no network access.
- `MT5BrokerAdapter` is **read-only**: `place_order` and `close_order` are
  hard-disabled (rejected with error 403). `get_orders` / `get_positions`
  perform genuine read-only retrieval via `orders_get()` / `positions_get()`
  (empty only when the broker reports none). It never calls `order_send` or
  `order_check`.
- `MT5BrokerAdapter` accepts **demo accounts only** (`trade_mode == 0`). A live
  account raises `MT5LiveAccountError` and shuts the connection down before any
  data is retrieved.
- MT5 market data is tagged `DataSource.LIVE` and flows through the Phase 2
  validator — never mislabeled as simulated/historical.
- Live routing remains gated by `live_locked`.

## Extending to Phase 6

1. Add `src/risk/` with `RiskManager` implementation (position sizing,
   SL/TP, daily loss limits).
2. Wire risk manager into `TradeExecutionEngine` for order validation.
3. Strategies remain signal-only; risk/execution handled in later phases.

## Phase 5 — Strategy Engine

| Module | File | Responsibility |
|--------|------|----------------|
| Signal model | `src/strategies/base.py` | `Signal`, `SignalDirection`, `SignalStatus`, `MarketRegime`, `Strategy` ABC, `StrategyResult`, `SignalRejection` |
| Registry | `src/strategies/registry.py` | `StrategyRegistry` — register/get/exists/enable/disable/list/parameters/strategy_info |
| Models | `src/strategies/models.py` | `StrategyParameters`, `ConfirmationCondition`, `ConfirmationRule`, `IndicatorSnapshot` |
| Service | `src/strategies/service.py` | `SignalService` — indicator→strategy bridge, market regime detection, signal construction |
| Signal generator | `src/strategies/signal_generator.py` | `ConfirmationEvaluator`, `SignalGenerator` — multi-indicator confirmation rules |
| Manager | `src/strategies/manager.py` | `StrategyManager` — fault-isolated execution, conflict detection, aggregation |
| Conflict resolver | `src/strategies/conflict_resolver.py` | `SignalConflictResolver` — conflict detection + aggregation policies |
| Market regime | `src/strategies/market_regime.py` | `MarketRegimeDetector` — TRENDING/RANGING/HIGH_VOLATILITY/LOW_VOLATILITY/TRANSITIONING/UNKNOWN |
| Trend following | `src/strategies/trend_following/trend_following.py` | `TrendFollowingStrategy` — EMA/SMA/ADX/MACD/RSI trend continuation/pullback |
| Price action | `src/strategies/price_action/price_action.py` | `PriceActionStrategy` — engulfing, pin bars, BOS, CHoCH, support/resistance rejection |
| Liquidity hunting | `src/strategies/liquidity/liquidity_hunting.py` | `LiquidityHuntingStrategy` — equal highs/lows, sweeps, close-back-inside |
| Trendline | `src/strategies/trendline/trendline.py` | `TrendlineStrategy` — swing pivots, trendlines, touches, breakouts, retests |
| Daily high/low | `src/strategies/daily_levels/daily_high_low.py` | `DailyHighLowStrategy` — prev day/week H/L breakouts and rejections |
| Scalping profile | `src/strategies/scalping/scalping_profile.py` | `ScalpingProfile` — M1/M5/M15 short-term profiles |
| Intraday profile | `src/strategies/intraday/intraday_profile.py` | `IntradayProfile` — M5/M15/M30/H1 session-aware profiles |
| Swing profile | `src/strategies/swing/swing_profile.py` | `SwingProfile` — H1/H4/D1/W1 multi-day profiles |

### Data flow (Phase 5)

```
MarketDataService -> IndicatorEngine -> SignalService ->
  MarketRegimeDetector -> Individual Strategies ->
  StrategyManager (fault-isolated) ->
  SignalConflictResolver ->
  Standardized Signals (no order execution)
```

### Design

- **Signal-only**: Strategies produce `Signal` objects (LONG/SHORT/NONE),
  never `OrderRequest`. No order placement, modification, or closing.
- **Fault isolation**: `StrategyManager` wraps each strategy in try/except;
  one failure does not crash the system. Errors are logged and recorded.
- **Look-ahead safe**: Completed candles only by default; `allow_incomplete`
  opt-in via the Phase 4 IndicatorEngine.
- **Decimal arithmetic**: All price calculations use `Decimal`.
- **Multi-timeframe**: Entry timeframe + confirmation timeframes explicitly
  tracked in every signal.
- **Market regime**: Strategies declare supported regimes; mismatched regimes
  produce rejections, not signals.
- **Conflict preservation**: Conflicting signals are reported, not resolved
  by forcing a trade decision.

### Inter-module dependencies

- `src/strategies/base.py` — depends on `src/indicators/base.py`,
  `src/market_data/models.py`.
- `src/strategies/registry.py` — depends on `src/strategies/base.py`.
- `src/strategies/models.py` — depends on `src/indicators/base.py`,
  `src/market_data/models.py`.
- `src/strategies/market_regime.py` — depends on `src/indicators/service.py`,
  `src/indicators/base.py`, `src/market_data/models.py`.
- `src/strategies/signal_generator.py` — depends on `src/indicators/base.py`,
  `src/market_data/models.py`, `src/strategies/models.py`.
- `src/strategies/service.py` — depends on all strategy modules +
  `src/indicators/service.py`.
- `src/strategies/manager.py` — depends on all strategy modules +
  `src/strategies/service.py`, `src/strategies/conflict_resolver.py`.
- `src/strategies/conflict_resolver.py` — depends on `src/strategies/base.py`.
- `src/strategies/{trend_following,price_action,liquidity,trendline,daily_levels,scalping,intraday,swing}/*.py` — depend on `base.py`, `models.py`, `service.py`, `src/indicators/service.py`.
- `src/strategies/__init__.py` — wires `create_strategy_manager()` factory.

### Safety boundaries (Phase 5)

- Strategies never call `place_order`, `close_order`, `order_send`, or
  `order_check`. They return `Signal` objects only.
- `ENABLE_LIVE_TRADING` remains `False`; `live_locked` stays active.
- No account switching, no live login.
- All data source provenance preserved
  (`DataSource.SIMULATED`/`HISTORICAL`/`LIVE`).

### Signal Lifecycle Management (Phase 5 Quality Audit)

Every signal carries full lifecycle management:

- **Unique identification**: `signal_id` (UUID4) plus `duplicate_key` for
  deduplication across strategy runs.
- **Creation timestamp**: `signal_timestamp` (UTC) recorded at generation.
- **Validity period**: `signal_valid_until` computed from
  `max_signal_age_minutes`; `is_expired()` check available.
- **Invalidation**: `technical_invalidation` price level; `is_invalidated(price)`
  checks if price has crossed the invalidation threshold.
- **Duplicate prevention**: `duplicate_key` combines strategy + symbol +
  timeframe + market data timestamp; `SignalService` tracks seen keys and
  rejects duplicates.
- **Status tracking**: `ACTIVE`, `EXPIRED`, `REJECTED`, `NO_SIGNAL`; only
  `ACTIVE` and non-expired signals are actionable.

### Signal Quality Validation (Phase 5 Quality Audit)

Before analysis, `SignalService.validate_signal_prerequisites()` verifies:

- Sufficient candle count (configurable minimum).
- Valid OHLC relationships (high >= low, high >= open/close, low <= open/close).
- Completed candles only (incomplete/forming bars excluded by default).
- Data freshness (max staleness in minutes).
- Required indicator availability and readiness.

Failures produce `SignalRejection` with a machine-readable category
(`insufficient_data`, `invalid_ohlc`, `incomplete_candle`, `stale_data`,
`unsupported_timeframe`, `unavailable_indicator`, `invalid_configuration`,
`regime_unsupported`, `strategy_error`, `duplicate_signal`, `no_signal_condition`)
and a human-readable reason. Rejections are never silently discarded.

### Strategy Versioning (Phase 5 Quality Audit)

- `strategy_name` and `strategy_version` on every signal.
- `config_fingerprint`: SHA-256 hash of strategy parameters for
  reproducibility. Historical signals can be traced to the exact
  parameter configuration.
- `compute_config_fingerprint()` utility in `src/strategies/models.py`.

### Risk Management Integration Contract (Phase 5 → Phase 6)

`RiskInterfaceSignal` is the standardized boundary between Phase 5
(Strategy Engine) and Phase 6 (Risk Management Engine). Phase 5 produces
signals; Phase 6 consumes them for risk evaluation, position sizing, and
stop-loss/take-profit calculation. No order execution occurs at this boundary.

Fields include: signal_id, strategy_name, strategy_version,
config_fingerprint, symbol, instrument_type, direction, signal_timestamp,
signal_valid_until, market_data_timestamp, reference_price,
technical_invalidation, market_regime, confirmation_conditions,
failed_conditions, explanation, expiry_conditions, data_source,
indicator_snapshot, parameters, entry_timeframe, confirmation_timeframes.

Responsibility separation:
- Phase 5: Signal generation only (no order placement, no risk calculation).
- Phase 6: Risk evaluation, position sizing, SL/TP, exposure limits.

### Signal Explainability

Every signal includes:
- Strategy name and version
- Indicators used (snapshot with values)
- Conditions satisfied and failed
- Timeframes considered (entry + confirmation)
- Market regime detected
- Explanation string
- Technical invalidation level (NOT a stop-loss)
- Expiry conditions

## Phase 6 — Advanced Risk Management Engine

### Overview

Phase 6 is a **risk-evaluation-only** engine. It consumes Phase 5 `Signal` /
`RiskInterfaceSignal` proposals and produces structured `RiskDecision` objects.
It never places, modifies, or closes orders. A `RISK_APPROVED` decision means
the hypothetical proposal passed all configured risk checks — it does **not**
authorize execution.

### Module overview

| Module | File | Responsibility |
|--------|------|----------------|
| Base | `src/risk_management/base.py` | Enums, `RiskParameters`, `RiskDecision`, `AccountSnapshot`, `PositionExposure`, `CircuitBreakerState`, `RiskEngineABC` |
| Models | `src/risk_management/models.py` | `DrawdownState`, `DailyPnLState`, `ExposureSummary`, `CorrelationResult`, `RiskReport` |
| Config | `src/risk_management/config.py` | `RiskPolicy` (validated), `InstrumentGroup`, `AssetClass`, deterministic `test_policy()` |
| Service | `src/risk_management/service.py` | `RiskEngine` — full evaluation pipeline + report building |
| Validator | `src/risk_management/validator.py` | Signal/account/instrument/policy pre-validation |
| Position sizing | `src/risk_management/position_sizing.py` | Instrument-aware volume (round DOWN to lot step), risk-per-lot, currency conversion |
| Stop-loss | `src/risk_management/stop_loss.py` | Stop validation (side, distance, limits), `calculate_stop_price` |
| Take-profit | `src/risk_management/take_profit.py` | TP validation (side, R:R), target derivation |
| Exposure | `src/risk_management/exposure.py` | Per-position and aggregated portfolio exposure |
| Portfolio risk | `src/risk_management/portfolio_risk.py` | Max positions, portfolio risk, instrument/asset-class/directional limits |
| Drawdown | `src/risk_management/drawdown.py` | High-watermark tracking, drawdown %, persisted state |
| Correlation | `src/risk_management/correlation.py` | Pearson correlation, configurable window/threshold |
| Margin | `src/risk_management/margin.py` | Required vs free margin, margin-usage limits |
| Circuit breaker | `src/risk_management/circuit_breaker.py` | Lockouts, audit history, trigger timestamp, authorized reset |
| Risk report | `src/risk_management/risk_report.py` | Decision/report serialization + text formatting |
| Persistence | `src/risk_management/persistence.py` | Atomic save/load of breaker, drawdown, daily PnL state |

### Data flow (Phase 6)

```
Phase 5 Signal (RiskInterfaceSignal)
  └─> RiskEngine.evaluate_signal()
        ├─ 1. Signal validation        (validator.py)
        ├─ 2. Account & instrument info (validator.py)
        ├─ 3. Stop-loss validation     (stop_loss.py)
        ├─ 4. Position sizing          (position_sizing.py)
        ├─ 5. Take-profit validation   (take_profit.py)
        ├─ 6. Portfolio exposure       (portfolio_risk.py)
        ├─ 7. Daily loss & drawdown    (drawdown.py)
        ├─ 8. Margin & spread          (margin.py)
        ├─ 9. Central risk decision    (service.py)
        └─ 10. Risk report             (risk_report.py)
  └─> RiskDecision (RISK_APPROVED | RISK_REJECTED | REQUIRES_INFORMATION |
      RISK_LOCKED | CALCULATION_UNAVAILABLE)
```

### Design

- **Decimal arithmetic** throughout; no floating-point drift.
- **Instrument-aware**: Forex, metals, energy, indices supported via broker
  volume min/max/step, contract size, tick value, and account-currency
  conversion. Missing essential specs are never guessed — rejected with a clear
  explanation.
- **Volume rounded DOWN** to the lot step; never rounded up beyond the risk
  budget. Volume below broker minimum → rejected.
- **Stop-loss**: LONG below entry / SHORT above entry; positive distance;
  min/max distance and %-of-entry limits; technical-invalidation / ATR /
  swing / fixed methods. A technical invalidation level is never silently moved
  to force an acceptable size.
- **Take-profit**: reward-to-risk / ATR / technical targets; minimum R:R
  enforced; LONG above entry / SHORT below entry.
- **Daily loss**: starting-reference equity/balance, realized + unrealized PnL,
  deposits/withdrawals excluded from PnL, configurable limit + lockout.
- **Drawdown**: equity & balance high-watermarks persisted to disk so a restart
  cannot reset protection limits; fail-safe if state unavailable.
- **Portfolio exposure**: max positions, portfolio risk, per-instrument and
  per-asset-class limits, directional exposure.
- **Correlation**: Pearson correlation with configurable window/threshold;
  insufficient data does not trigger rejection unless policy requires it.
- **Margin**: required vs free margin, projected margin-usage limit, leverage.
- **Circuit breakers**: audit history, trigger timestamp, lockout-until, explicit
  authorized reset — not auto-cleared on restart.
- **Decision statuses**: `RISK_APPROVED`, `RISK_REJECTED`,
  `REQUIRES_INFORMATION`, `RISK_LOCKED`, `CALCULATION_UNAVAILABLE`.
- **Execution boundary**: zero imports of order-execution functions;
  `place_order`/`close_order`/`order_send`/`order_check` are never called.
  Account/position data is read-only.

### Inter-module dependencies

- `src/risk_management/base.py` — depends on `src/market_data/models.py`
  (InstrumentSpec) only.
- `src/risk_management/config.py` — depends on `base.py`.
- `src/risk_management/validator.py` — depends on `base.py`, `config.py`,
  `market_data/models.py`.
- `src/risk_management/position_sizing.py` — depends on `base.py`, `config.py`,
  `market_data/models.py`.
- `src/risk_management/stop_loss.py` — depends on `base.py`, `config.py`,
  `position_sizing.py`.
- `src/risk_management/take_profit.py` — depends on `base.py`, `config.py`.
- `src/risk_management/exposure.py` — depends on `src/models.py` (Position),
  `models.py` (PositionExposure).
- `src/risk_management/portfolio_risk.py` — depends on `config.py`, `models.py`,
  `exposure.py`.
- `src/risk_management/drawdown.py` — depends on `models.py` (DrawdownState).
- `src/risk_management/correlation.py` — depends on `config.py`, `models.py`.
- `src/risk_management/margin.py` — depends on `base.py` (MarginSnapshot),
  `config.py`.
- `src/risk_management/circuit_breaker.py` — depends on `base.py`.
- `src/risk_management/service.py` — depends on all risk_management modules +
  `src/models.py`, `src/market_data/models.py`.
- `src/risk_management/risk_report.py` — depends on `base.py`, `models.py`.
- `src/risk_management/persistence.py` — depends on `base.py`, `models.py`.

### Safety boundaries

- No order placement, modification, or closing — ever.
- No `order_send` / `order_check` calls.
- No automatic liquidation or position closing.
- No live trading; `live_locked` remains active.
- No broker passwords or credentials stored.
- No automatic account switching.
- Risk-approved proposals are NOT executed during Phase 6.
- Missing account/position/spec data fails safely (REQUIRES_INFORMATION or
  CALCULATION_UNAVAILABLE), never silently treated as zero.
- Circuit-breaker lockouts persist across restarts and require explicit
  authorized reset.

## Phase 7 — News & Economic Calendar Engine

### Overview

Phase 7 is a **news/risk-information-only** engine. It collects, normalizes and
evaluates economic-calendar events and news, and communicates event-related
restrictions to the Phase 6 Risk Management Engine. It never places, modifies
or closes orders and never executes trades. Importance is never inferred from an
event name, and missing values/times are never fabricated.

### Module overview

| Module | File | Responsibility |
|--------|------|----------------|
| Base | `src/news/base.py` | `CalendarProvider`, `NewsProvider`, `NewsEngineABC`; enums `Importance`, `EventStatus`, `NewsWindowStatus`, `EventCategory`, `UnavailablePolicy` |
| Models | `src/news/models.py` | `EconomicEvent`, `NewsArticle`, `ImpactAssessment`, `NewsRiskContext` (immutable; UTC timestamps; unresolved-time flag) |
| Config | `src/news/config.py` | `NewsConfig` — per-importance pre/post windows, category overrides, caution threshold, stale timeout, unavailable policy, leakage prevention, currency/instrument relevance rules |
| Registry | `src/news/registry.py` | Keyword→category rules (`CategoryRegistry`) for inflation/employment/central-bank/growth/commodities |
| Normalization | `src/news/normalization.py` | Raw provider payload → `EconomicEvent` (missing values stay `None`) |
| Calendar | `src/news/calendar/{event_mapping,impact,scheduler,revisions,economic_events}.py` | Instrument↔currency relevance, impact assessment, relevant-event scheduling, revision merge + dedup, in-memory store |
| Providers | `src/news/providers/{mock,csv,mt5_calendar,api,rss}_provider.py` | Deterministic mock, historical CSV, MQL5-export bridge (server-tz→UTC), licensed API & permitted RSS interfaces |
| Filters | `src/news/filters/{relevance,news_window,restriction}.py` | Relevance filtering, consolidated window status (precedence), `build_news_risk_context` |
| Persistence | `src/news/persistence/{repository,event_history}.py` | Dedup, revision merge, range/unresolved queries, revision timeline |
| Risk integration | `src/news/risk_integration/news_risk_context.py` | Summarize `NewsRiskContext` for the risk engine / operators |
| Service | `src/news/service.py` | `NewsService` — provider collection, storage, freshness/staleness, `risk_context()`, leakage-safe `events_as_of()` |

### Data flow (Phase 7)

```
Provider.get_events(start, end) -> normalize_event -> EventRepository (dedup/merge)
  -> NewsService.risk_context(instrument)
       ├─ filter relevant events (relevance.py)
       ├─ compute_news_window_status (news_window.py)
       └─ build_news_risk_context (restriction.py) -> NewsRiskContext
  -> RiskEngine.evaluate_signal(..., news_context=ctx)   # optional, backward-compatible
       ├─ BLOCK_NEW_ENTRIES / EVENT_TIME_UNCERTAIN / NEWS_DATA_UNAVAILABLE -> REJECTED
       ├─ NEWS_CAUTION -> warning only
       └─ NEWS_CLEAR / None -> no news gate
```

### Timezone handling

MQL5 economic-calendar timestamps use **trading-server time**, not UTC.
`MT5CalendarProvider` converts server time → UTC **only** when a verified
`server_timezone` is configured (DST-aware via the IANA `tzdata` package). When
the server timezone cannot be verified, `time_resolved` is `False` and the event
is treated as EVENT_TIME_UNCERTAIN — never as a precise window.

### Design

- **Backward-compatible**: `RiskEngine.evaluate_signal(..., news_context=None)`
  keeps all prior behavior; the news gate only applies when a context is passed.
- **Leakage-safe**: `NewsService.events_as_of(as_of, ...)` excludes events whose
  information did not yet exist (future retrieval/publication) for backtests.
- **No fabrication**: missing actual/forecast/previous values and unresolved
  times are preserved as `None`/flags, never guessed.
- **Read-only**: no order placement/modification/closing; no live trading; no
  scraping; credentials via environment variables only.

### Safety boundaries (Phase 7)

- Never places, modifies or closes orders; never executes trades.
- No account switching, no live login, no broker password storage.
- Simulated providers are labeled `is_simulated=True` and never presented as
  genuine data.
- External API/RSS providers are interfaces only; no network access in tests.

## Extending to later phases (execution / backtesting)

1. Consume `RiskDecision` from `RiskEngine.evaluate_signal()` (optionally with a
   Phase 7 `NewsRiskContext`).
2. Only act on `RISK_APPROVED` (still hypothetical — confirmation required).
3. Route through `TradeExecutionEngine` with `live_locked` gate.
4. Keep risk, news, and execution in separate modules; execution imports risk,
   not vice versa.
