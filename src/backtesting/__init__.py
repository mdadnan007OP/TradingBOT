"""Phase 8 — Backtesting Engine.

Event-driven historical simulation that reuses the Phase 4 (indicators),
Phase 5 (strategies), Phase 6 (risk) and Phase 7 (news) engines. It NEVER
places real or demo broker orders and never calls any MT5 execution function.

All results are simulated historical backtest results — not guarantees of
future performance.
"""

from __future__ import annotations

from src.backtesting.config import (
    AccountConfig,
    BacktestConfig,
    CommissionConfig,
    DataConfig,
    ExecutionConfig,
    SlippageConfig,
    SpreadConfig,
    SwapConfig,
    default_backtest_config,
    test_backtest_config,
)
from src.backtesting.engine import BacktestEngine
from src.backtesting.models import (
    BacktestEvent,
    BacktestResult,
    ClosedTrade,
    EquityPoint,
    ExitReason,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionStatus,
    SimulatedOrder,
    SimulatedPosition,
)
from src.backtesting.quality_report import (
    BacktestQualityReport,
    ExecutionFidelity,
    build_quality_report,
)

__all__ = [
    "BacktestEngine",
    "BacktestConfig",
    "AccountConfig",
    "ExecutionConfig",
    "SpreadConfig",
    "SlippageConfig",
    "CommissionConfig",
    "SwapConfig",
    "DataConfig",
    "default_backtest_config",
    "test_backtest_config",
    "BacktestResult",
    "BacktestEvent",
    "ClosedTrade",
    "EquityPoint",
    "SimulatedOrder",
    "SimulatedPosition",
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "PositionStatus",
    "ExitReason",
    "BacktestQualityReport",
    "ExecutionFidelity",
    "build_quality_report",
]