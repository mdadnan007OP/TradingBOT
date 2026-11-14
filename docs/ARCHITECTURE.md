# Architecture — Forex Trading Bot (Phases 1 & 2)

This document explains how the modules communicate and the design rationale
behind the Phase 1 foundation and Phase 2 Market Data Engine.

## Design principles

1. **Separation of concerns** — each module has one responsibility.
2. **Interface-driven** — engines depend on ABCs, not concrete implementations.
3. **Broker-agnostic core** — business models know nothing about MT5 or PuPrime.
4. **Fail-safe by default** — missing data, connection failure, and unexpected
   errors degrade gracefully; live trading stays locked.
5. **No secrets** — credentials are never stored or logged.

## Module overview

### Phase 1 — Foundation

| Module | File | Responsibility |
|--------|------|----------------|
| Configuration | `src/config.py` | Centralized config + `.env` loading; trading-mode & safety flags |
| Logging | `src/logging_config.py` | Console + rotating-file logging |
| Data models | `src/models.py` | Instrument, Tick, Candle, Order, Position, AccountInfo, TradeResultModel |
| Broker integration | `src/broker.py` | `BrokerAdapter` ABC + `MockBrokerAdapter` |
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
  ├─ register_provider(MockMarketDataProvider | HistoricalCSVProvider | future MT5)
  ├─ provider.get_candles(symbol, timeframe, start, end) -> List[OHLCBar]
  ├─ DataProcessor.standardize(bars)        # sort, deduplicate
  ├─ DataValidator.validate_bars(...)       # quality report
  └─ return validated, standardized bars
```

Future flow (Phase 3+):

```
MarketDataEngine -> IndicatorEngine -> StrategyEngine -> RiskManager ->
TradeExecutionEngine -> BrokerAdapter -> (MT5 or Mock)
```

## Inter-module dependencies

### Phase 1 (unchanged)

- `config.py` — depends on nothing in `src` (loads env only).
- `logging_config.py` — depends on `config.py`.
- `models.py` — depends on nothing.
- `broker.py` — depends on `config.py`, `models.py`.
- `engines.py` — depends on `broker.py`, `models.py`.
- `execution.py` — depends on `config.py`, `broker.py`, `engines.py`, `models.py`.
- `main.py` — depends on `config.py`, `logging_config.py`, `broker.py`, `engines.py`, `execution.py`, `models.py`.

### Phase 2 (new)

- `market_data/models.py` — depends on nothing external.
- `market_data/base.py` — depends on `market_data/models.py`.
- `market_data/sessions.py` — depends on nothing external.
- `market_data/mock_provider.py` — depends on `config.py`, `market_data/base.py`, `market_data/models.py`.
- `market_data/csv_provider.py` — depends on `market_data/base.py`, `market_data/models.py`.
- `market_data/validator.py` — depends on `market_data/models.py`, `market_data/sessions.py`.
- `market_data/processor.py` — depends on `market_data/models.py`.
- `market_data/service.py` — depends on `market_data/base.py`, `market_data/models.py`, `market_data/processor.py`, `market_data/sessions.py`, `market_data/validator.py`.
- `market_data/demo.py` — depends on all market_data modules.

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
- No MT5, PuPrime, or real broker connections in Phase 2.
- Live routing remains gated by `live_locked`.

## Extending to Phase 3

1. Add `src/indicators/` with `IndicatorEngine` implementations (EMA, SMA, RSI, MACD, BB, ATR, ADX, Stochastic).
2. Add `src/strategies/` with `Strategy` implementations.
3. Add `src/risk/` with `RiskManager` implementation.
4. Add `src/mt5_broker.py` implementing `BrokerAdapter` using the MT5 library (Phase 3+).
5. Wire new engines into `main.py`.
