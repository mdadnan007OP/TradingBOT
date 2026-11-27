"""Centralized configuration management for the Forex trading bot.

Configuration is loaded from environment variables, with optional support for a
``.env`` file in the project root. All trading-mode and safety flags live here so
that business logic stays decoupled from configuration.

Live trading is disabled by default and remains locked until a later development
phase. No broker credentials or passwords are stored here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


def load_env_file(path: str = ".env") -> None:
    """Load environment variables from a ``.env`` file if it exists.

    This is a small stdlib-only loader (no ``python-dotenv`` dependency). Lines
    are parsed as ``KEY=VALUE``; comments and blank lines are ignored. Existing
    environment variables are never overwritten by the file, so the real
    environment takes precedence.

    Args:
        path: Path to the ``.env`` file.
    """
    if not os.path.isfile(path):
        return

    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def get_bool(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable.

    Accepts ``true/false``, ``1/0``, ``yes/no`` (case-insensitive).
    """
    raw = os.environ.get(name, str(default)).strip().lower()
    return raw in ("true", "1", "yes", "on")


def get_float(name: str, default: float) -> float:
    """Read a float environment variable, returning ``default`` on parse error."""
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def get_int(name: str, default: int) -> int:
    """Read an int environment variable, returning ``default`` on parse error."""
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def get_list(name: str, default: List[str] | None = None) -> List[str]:
    """Read a comma-separated list environment variable."""
    if default is None:
        default = []
    raw = os.environ.get(name, "")
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class TradingConfig:
    """Trading-mode and safety configuration.

    Attributes:
        mode: One of ``simulation``, ``demo``, or ``live``.
        enable_live_trading: Master kill-switch for live order placement.
            Must remain ``False`` until a later phase.
        default_symbols: Instrument symbols the bot is configured to watch.
    """

    mode: str = "simulation"
    enable_live_trading: bool = False
    default_symbols: List[str] = field(default_factory=lambda: ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY"])

    @property
    def is_live(self) -> bool:
        """Return True only when live trading is explicitly enabled AND unlocked."""
        return self.enable_live_trading and self.mode == "live"

    @property
    def live_locked(self) -> bool:
        """Return True when live trading is not permitted in this phase."""
        return not self.enable_live_trading or self.mode != "live"


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    dir: str = "logs"


@dataclass(frozen=True)
class RiskConfig:
    """Centralized risk-management defaults.

    These are defaults only; the risk engine applies its own validation and
    limits at runtime. Values are expressed as decimals (e.g. 0.01 = 1%).
    """

    risk_per_trade: float = 0.01
    max_daily_loss: float = 0.05
    max_positions: int = 5


def _default_monitoring_config() -> MonitoringConfig:
    """Lazy default factory for MonitoringConfig (avoids circular import)."""
    from src.monitoring.config import MonitoringConfig

    return MonitoringConfig()


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration, composed of domain sub-configs."""

    trading: TradingConfig
    logging: LoggingConfig
    risk: RiskConfig
    monitoring: MonitoringConfig = field(default_factory=_default_monitoring_config)

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Build configuration from environment variables (and optional ``.env``)."""
        load_env_file()
        # Lazy import to avoid circular imports (config -> monitoring -> execution -> broker -> config).
        from src.monitoring.config import MonitoringConfig

        return cls(
            trading=TradingConfig(
                mode=os.environ.get("TRADING_MODE", "simulation"),
                enable_live_trading=get_bool("ENABLE_LIVE_TRADING", False),
                default_symbols=get_list(
                    "DEFAULT_SYMBOLS",
                    ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY"],
                ),
            ),
            logging=LoggingConfig(
                level=os.environ.get("LOG_LEVEL", "INFO"),
                dir=os.environ.get("LOG_DIR", "logs"),
            ),
            risk=RiskConfig(
                risk_per_trade=get_float("DEFAULT_RISK_PER_TRADE", 0.01),
                max_daily_loss=get_float("MAX_DAILY_LOSS", 0.05),
                max_positions=get_int("MAX_POSITIONS", 5),
            ),
            monitoring=MonitoringConfig.from_env(),
        )


# Module-level singleton loaded once at import time.
CONFIG: AppConfig = AppConfig.from_env()
