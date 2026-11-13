"""Engine interfaces.

Abstract base classes defining the contracts for each engine module. Concrete
implementations are developed in later phases. Phase 1 ships only the interfaces
and the mock broker adapter; these interfaces declare what each engine *must*
provide without prescribing how.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from src.broker import BrokerAdapter
from src.models import Candle, Instrument, OrderRequest, Position, Tick, TradeResultModel


# ---------------------------------------------------------------------------
# Market Data Engine
# ---------------------------------------------------------------------------


class MarketDataEngine(ABC):
    """Collects and validates price and candle data."""

    @abstractmethod
    def get_tick(self, symbol: str) -> Optional[Tick]:
        ...

    @abstractmethod
    def get_candles(self, symbol: str, count: int) -> List[Candle]:
        ...

    @abstractmethod
    def subscribe(self, symbol: str) -> bool:
        ...

    @abstractmethod
    def is_ready(self) -> bool:
        ...


# ---------------------------------------------------------------------------
# Technical Indicator Engine
# ---------------------------------------------------------------------------


class IndicatorEngine(ABC):
    """Computes technical indicators from candle/tick data."""

    @abstractmethod
    def compute(
        self,
        name: str,
        symbol: str,
        candles: List[Candle],
        **params: object,
    ) -> Dict[str, List[float]]:
        ...

    @abstractmethod
    def supported_indicators(self) -> List[str]:
        ...


# ---------------------------------------------------------------------------
# Strategy Engine
# ---------------------------------------------------------------------------


class Strategy(ABC):
    """A single trading strategy.

    Strategies are independent, testable, and enabled/disabled individually.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def enabled(self) -> bool:
        ...

    @abstractmethod
    def on_tick(self, tick: Tick) -> Optional[OrderRequest]:
        ...

    @abstractmethod
    def on_candle(self, candle: Candle) -> Optional[OrderRequest]:
        ...


class StrategyEngine(ABC):
    """Manages the lifecycle of strategies."""

    @abstractmethod
    def register(self, strategy: Strategy) -> bool:
        ...

    @abstractmethod
    def enable(self, name: str) -> bool:
        ...

    @abstractmethod
    def disable(self, name: str) -> bool:
        ...

    @abstractmethod
    def on_tick(self, tick: Tick) -> List[OrderRequest]:
        ...

    @abstractmethod
    def on_candle(self, candle: Candle) -> List[OrderRequest]:
        ...


# ---------------------------------------------------------------------------
# Risk Management Engine
# ---------------------------------------------------------------------------


class RiskManager(ABC):
    """Centralized risk-management interface.

    Validates order requests, computes position sizing, and enforces exposure
    and daily-loss limits.
    """

    @abstractmethod
    def validate(self, request: OrderRequest, positions: List[Position]) -> TradeResultModel:
        ...

    @abstractmethod
    def compute_position_size(
        self,
        symbol: str,
        side: object,
        stop_loss_distance: object,
        account_equity: object,
    ) -> object:
        ...

    @abstractmethod
    def daily_loss_limit_reached(self) -> bool:
        ...

    @abstractmethod
    def max_positions_reached(self, positions: List[Position]) -> bool:
        ...


# ---------------------------------------------------------------------------
# News and Economic Calendar Engine
# ---------------------------------------------------------------------------


class NewsEngine(ABC):
    """Handles economic events and trading restrictions around announcements."""

    @abstractmethod
    def get_upcoming_events(self) -> List[dict]:
        ...

    @abstractmethod
    def is_trading_allowed(self, symbol: str) -> bool:
        ...

    @abstractmethod
    def minutes_to_next_high_impact_event(self, symbol: str) -> Optional[int]:
        ...


# ---------------------------------------------------------------------------
# Trade Execution Engine
# ---------------------------------------------------------------------------


class TradeExecutionEngine(ABC):
    """Validates and routes trade requests through the broker adapter."""

    @abstractmethod
    def execute(self, request: OrderRequest) -> TradeResultModel:
        ...

    @abstractmethod
    def close_position(self, ticket: str) -> TradeResultModel:
        ...


# ---------------------------------------------------------------------------
# Backtesting Engine
# ---------------------------------------------------------------------------


class BacktestingEngine(ABC):
    """Evaluates strategies against historical market data."""

    @abstractmethod
    def run(self, symbol: str, candles: List[Candle]) -> dict:
        ...


# ---------------------------------------------------------------------------
# Paper / Demo Trading Engine
# ---------------------------------------------------------------------------


class PaperTradingEngine(ABC):
    """Tests strategies without risking real funds."""

    @abstractmethod
    def start(self) -> bool:
        ...

    @abstractmethod
    def stop(self) -> bool:
        ...

    @abstractmethod
    def is_running(self) -> bool:
        ...


# ---------------------------------------------------------------------------
# Monitoring and Reporting Engine
# ---------------------------------------------------------------------------


class MonitoringEngine(ABC):
    """Records trades, errors, performance, and system status."""

    @abstractmethod
    def record_trade(self, result: TradeResultModel) -> None:
        ...

    @abstractmethod
    def record_error(self, error: Exception, context: Optional[dict] = None) -> None:
        ...

    @abstractmethod
    def generate_report(self) -> dict:
        ...
