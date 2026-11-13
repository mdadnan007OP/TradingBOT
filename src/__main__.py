"""Forex Trading Bot — Phase 1 Foundation

Professional, modular foundation for an automated Forex trading system intended
to connect to MetaTrader 5 (MT5) and the PuPrime broker account. Phase 1
establishes structure, configuration, data models, a mock broker adapter, and
engine interfaces. **No real orders are placed and live trading is disabled.**

> **Disclaimer:** This software is for educational and development purposes. It
> does not guarantee profits, and automated trading carries substantial risk of
> loss. Never trade capital you cannot afford to lose.

## Environment

- **OS:** Windows
- **Python:** 3.13.15
- **pip:** 26.2.1
- **Git:** 2.55.0
- **IDE:** Google Antigravity (recommended)
- **Trading platform (target):** MetaTrader 5
- **Intended broker:** PuPrime

Phase 1 uses only the Python standard library (no `pip install` required).
Later phases will add `pandas`, `numpy`, and the MT5 integration.

## Project structure

```
forex-trading-bot/
├── .env.example            # Copy to .env and fill in your values (never commit .env)
├ .gitignore
├ pyproject.toml          # Package metadata
├ README.md               # This file
├ docs/
│   ├── ARCHITECTURE.md     # Module communication & design
│   ├── ROADMAP.md          # Phase-by-phase development plan
│   └── RISK_AND_SAFETY.md  # Safety rules & fail-safes
├ src/                    # Application source (package)
│   ├── __init__.py
│   ├── __main__.py         # Allows `python -m src` to work
│   ├── config.py           # Centralized configuration + env loading
│   ├── logging_config.py   # Logging setup (console + rotating file)
│   ├── models.py           # Data models (tick, candle, order, position, account)
│   ├── broker.py           # BrokerAdapter interface + MockBrokerAdapter
│   ├── engines.py          # Abstract interfaces for all 10 engine modules
│   ├── execution.py        # Trade execution engine (Phase 1 skeleton)
│   └── main.py             # Application entry point
├ tests/                  # Unit tests
│   └── test_foundation.py
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

## Run the tests

```powershell
python -m pytest tests/ -v
```

If `pytest` is not installed:

```powershell
pip install pytest
python -m pytest tests/ -v
```

## Safety (mandatory)

- Live trading is **disabled by default** (`ENABLE_LIVE_TRADING=false`, `TRADING_MODE=simulation`).
- No real orders are placed in Phase 1.
- No broker credentials are requested or stored.
- The mock broker is used for all testing.
- Live mode remains locked until a later development phase.
- No profitability promises; backtest results are not predictive.

See `docs/RISK_AND_SAFETY.md` for the full safety policy.

## What is implemented (Phase 1)

- Project folder structure
- Centralized config management with `.env` support
- Data models (Instrument, Tick, Candle, Order, Position, AccountInfo, etc.)
- Logging system (console + rotating file)
- Broker adapter interface + MockBrokerAdapter
- Trade execution engine with live-trade lock
- Engine interfaces for all 10 modules
- Application entry point (`src/main.py`)
- Unit tests
- Documentation (README, architecture, roadmap, risk & safety)

## What remains (Phase 2+)

See `docs/ROADMAP.md`. Highlights:

- MT5 broker adapter (replace/stub the mock adapter)
- Technical indicator engine (EMA, SMA, RSI, MACD, BB, ATR, ADX, Stochastic)
- Strategy engine + concrete strategies
- Risk management engine (position sizing, SL/TP, daily loss limits)
- News/economic calendar engine (legitimate sources only, respect terms of use)
- Backtesting engine
- Paper/demo trading engine
- Monitoring & reporting engine

## License

MIT
"""