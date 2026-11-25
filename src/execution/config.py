"""Phase 9 execution configuration.

All execution-mode and safety configuration lives here so business logic stays
decoupled from configuration. Live trading is permanently disabled. DEMO_AUTO
remains disabled unless explicitly enabled via environment AND command-line flag.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import List


class ExecutionMode(str, Enum):
    """Permitted execution modes. LIVE is intentionally absent."""

    PAPER = "PAPER"
    DEMO_MANUAL = "DEMO_MANUAL"
    DEMO_AUTO = "DEMO_AUTO"


def get_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, str(default)).strip().lower()
    return raw in ("true", "1", "yes", "on")


def get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def get_decimal(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def get_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def get_list(name: str, default: List[str] | None = None) -> List[str]:
    if default is None:
        default = []
    raw = os.environ.get(name, "")
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class ExecutionConfig:
    """Execution-mode and safety configuration (fail-closed)."""

    mode: ExecutionMode = ExecutionMode.PAPER
    demo_execution_enabled: bool = False
    demo_manual_approval_required: bool = True
    demo_automatic_enabled: bool = False
    allowed_demo_server: str = ""
    allowed_broker_company: str = ""
    magic_number: int = 0
    max_demo_orders_per_day: int = 0
    max_demo_open_positions: int = 0
    max_demo_order_volume: str = "0"
    max_demo_daily_risk: str = "0"
    demo_approval_ttl_seconds: int = 300
    max_spread_pips: Decimal | None = None
    max_deviation_points: int = 0
    order_timeout_seconds: int = 30
    enable_external_python_api: bool = False

    def __post_init__(self) -> None:
        # Fail-closed validation.
        if self.mode == ExecutionMode.DEMO_AUTO and not self.demo_automatic_enabled:
            raise ValueError("DEMO_AUTO requires DEMO_AUTOMATIC_ENABLED=true")
        if self.mode == ExecutionMode.DEMO_MANUAL and not self.demo_execution_enabled:
            raise ValueError("DEMO_MANUAL requires DEMO_EXECUTION_ENABLED=true")
        if self.mode == ExecutionMode.PAPER and self.demo_execution_enabled:
            raise ValueError("PAPER mode must not enable demo execution")
        # LIVE is not a valid mode; reject explicitly.
        live = get_str("EXECUTION_MODE", "").upper()
        if live in ("LIVE", "REAL"):
            raise ValueError("LIVE/REAL execution mode is not permitted")
        if self.magic_number <= 0 and self.mode != ExecutionMode.PAPER:
            raise ValueError("MT5_MAGIC_NUMBER must be > 0 for demo execution")
        if self.mode != ExecutionMode.PAPER and not self.allowed_demo_server:
            raise ValueError("MT5_ALLOWED_DEMO_SERVER must be set for demo execution")

    @property
    def demo_trading_permitted(self) -> bool:
        return self.mode in (ExecutionMode.DEMO_MANUAL, ExecutionMode.DEMO_AUTO)

    @property
    def automatic_permitted(self) -> bool:
        return (
            self.mode == ExecutionMode.DEMO_AUTO
            and self.demo_automatic_enabled
            and self.demo_execution_enabled
        )

    @classmethod
    def from_env(cls, cli_demo_auto: bool = False) -> "ExecutionConfig":
        mode_raw = get_str("EXECUTION_MODE", "PAPER").upper()
        try:
            mode = ExecutionMode[mode_raw]
        except KeyError:
            mode = ExecutionMode.PAPER

        return cls(
            mode=mode,
            demo_execution_enabled=get_bool("DEMO_EXECUTION_ENABLED", False),
            demo_manual_approval_required=get_bool("DEMO_MANUAL_APPROVAL_REQUIRED", True),
            demo_automatic_enabled=get_bool("DEMO_AUTOMATIC_ENABLED", False),
            allowed_demo_server=get_str("MT5_ALLOWED_DEMO_SERVER", ""),
            allowed_broker_company=get_str("MT5_ALLOWED_BROKER_COMPANY", ""),
            magic_number=get_int("MT5_MAGIC_NUMBER", 0),
            max_demo_orders_per_day=get_int("MAX_DEMO_ORDERS_PER_DAY", 0),
            max_demo_open_positions=get_int("MAX_DEMO_OPEN_POSITIONS", 0),
            max_demo_order_volume=get_decimal("MAX_DEMO_ORDER_VOLUME", "0"),
            max_demo_daily_risk=get_decimal("MAX_DEMO_DAILY_RISK", "0"),
            demo_approval_ttl_seconds=get_int("DEMO_APPROVAL_TTL_SECONDS", 300),
            max_spread_pips=None,
            max_deviation_points=get_int("MAX_DEVIATION_POINTS", 0),
            order_timeout_seconds=get_int("ORDER_TIMEOUT_SECONDS", 30),
            enable_external_python_api=get_bool("ENABLE_EXTERNAL_PYTHON_API", False),
        )
