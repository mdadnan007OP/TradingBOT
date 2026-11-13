# Architecture — Forex Trading Bot (Phase 1)

This document explains how the modules communicate and the design rationale
behind the Phase 1 foundation.

## Design principles

1. **Separation of concerns** — each module has one responsibility.
2. **Interface-driven** — engines depend on ABCs, not concrete implementations.
3. **Broker-agnostic core** — business models know nothing about MT5 or PuPrime.
4. **Fail-safe by default** — missing data, connection failure, and unexpected
   errors degrade gracefully; live trading stays locked.
5. **No secrets** — credentials are never stored or logged.

## Module overview

| Module | File | Responsibility |
|--------|------|----------------|
| Configuration | `src/config.py` | Centralized config + `.env` loading; trading-mode & safety flags |
| Logging | `src/logging_config.py` | Console + rotating-file logging |
| Data models | `src/models.py` | Instrument, Tick, Candle, Order, Position, AccountInfo, TradeResultModel |
| Broker integration | `src/broker.py` | `BrokerAdapter` ABC + `MockBrokerAdapter` |
| Engine interfaces | `src/engines.py` | Abstract interfaces for all 10 engine modules |
| Trade execution | `src/execution.py` | Routes orders through risk + broker with live-trade lock |
| Entry point | `src/main.py` | Wires config, logging, mock broker, execution engine |

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

No market data flows yet. In later phases, the flow will be:

```
MarketDataEngine -> IndicatorEngine -> StrategyEngine -> RiskManager ->
TradeExecutionEngine -> BrokerAdapter -> (MT5 or Mock)
```

## Inter-module dependencies

- `config.py` — depends on nothing in `src` (loads env only).
- `logging_config.py` — depends on `config.py`.
- `models.py` — depends on nothing.
- `broker.py` — depends on `config.py`, `models.py`.
- `engines.py` — depends on `broker.py`, `models.py`.
- `execution.py` — depends on `config.py`, `broker.py`, `engines.py`, `models.py`.
- `main.py` — depends on `config.py`, `logging_config.py`, `broker.py`, `engines.py`, `execution.py`, `models.py`.

There are no circular imports.

## Safety boundaries

- `CONFIG.trading.live_locked` is a master kill-switch. `TradeExecutionEngineImpl`
  rejects every `execute()` / `close_position()` call while `live_locked` is true.
- `MockBrokerAdapter` simulates only; it never contacts a real market or broker.
- The MT5 adapter (Phase 2) will implement `BrokerAdapter` and be selectable via
  config, but live routing remains gated by `live_locked`.

## Extending in Phase 2

1. Create `src/mt5_broker.py` implementing `BrokerAdapter` using the `metaapi`/`mt5` library.
2. Add concrete implementations under `src/indicators/`, `src/strategies/`,
   `src/risk/`, `src/news/`, `src/backtesting/`, `src/paper/`, `src/monitoring/`.
3. Wire them into `main.py` and update `TradeExecutionEngineImpl` to accept a
   real `RiskManager`.
