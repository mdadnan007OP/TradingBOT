"""StrategyManager — fault-isolated execution of multiple strategies.

Runs enabled strategies independently. One failed strategy does not crash
the system. Errors are logged and recorded in StrategyResult.error.

Provides signal lifecycle management:
    * Duplicate signal prevention across all strategies.
    * Signal expiration filtering.
    * Signal invalidation filtering.
    * Risk interface export for Phase 6 integration.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.indicators.service import IndicatorEngine
from src.market_data.models import DataSource, MarketTimeframe, OHLCBar
from src.strategies.base import (
    MarketRegime,
    Signal,
    SignalDirection,
    SignalStatus,
    Strategy,
    StrategyResult,
)
from src.strategies.conflict_resolver import SignalConflictResolver
from src.strategies.market_regime import MarketRegimeDetector
from src.strategies.models import RiskInterfaceSignal, StrategyParameters
from src.strategies.registry import StrategyRegistry
from src.strategies.service import SignalService

logger = logging.getLogger(__name__)


class StrategyManager:
    """Manages strategy lifecycle and execution with fault isolation.

    Responsibilities:
        * Register/enable/disable strategies.
        * Run enabled strategies independently.
        * Isolate strategy errors (one failure does not crash others).
        * Detect and resolve signal conflicts.
        * Aggregate signals across strategies.
    """

    def __init__(
        self,
        indicator_engine: IndicatorEngine,
        registry: Optional[StrategyRegistry] = None,
        conflict_resolver: Optional[SignalConflictResolver] = None,
        regime_detector: Optional[MarketRegimeDetector] = None,
    ) -> None:
        self._registry = registry or StrategyRegistry()
        self._service = SignalService(
            indicator_engine=indicator_engine,
            market_regime_detector=regime_detector or MarketRegimeDetector(),
        )
        self._conflict_resolver = conflict_resolver or SignalConflictResolver()
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    # ------------------------------------------------------------------
    # Registry delegation
    # ------------------------------------------------------------------

    @property
    def registry(self) -> StrategyRegistry:
        return self._registry

    def register_strategy(self, strategy: Strategy) -> bool:
        return self._registry.register(strategy)

    def unregister_strategy(self, name: str) -> bool:
        return self._registry.unregister(name)

    def enable_strategy(self, name: str) -> bool:
        return self._registry.enable(name)

    def disable_strategy(self, name: str) -> bool:
        return self._registry.disable(name)

    def is_enabled(self, name: str) -> bool:
        return self._registry.is_enabled(name)

    def set_strategy_parameters(self, name: str, parameters: Dict[str, Any]) -> bool:
        return self._registry.set_parameters(name, parameters)

    def list_strategies(self) -> List[Dict[str, Any]]:
        return [
            self._registry.strategy_info(name)
            for name in self._registry.supported_strategies()
        ]

    def list_enabled(self) -> List[str]:
        return self._registry.enabled_strategies()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run_strategy(
        self,
        strategy_name: str,
        symbol: str,
        candles_by_timeframe: Dict[MarketTimeframe, List[OHLCBar]],
        parameters: Optional[StrategyParameters] = None,
        data_source: DataSource = DataSource.SIMULATED,
    ) -> StrategyResult:
        """Run a single named strategy with fault isolation."""
        strategy = self._registry.get(strategy_name)
        if strategy is None:
            entry_tf = (
                candles_by_timeframe.keys()[0] if candles_by_timeframe else MarketTimeframe.M1
            )
            return StrategyResult(
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=entry_tf,
                signals=[],
                rejections=[],
                market_regime=MarketRegime.UNKNOWN,
                indicator_snapshots={},
                error=f"Strategy '{strategy_name}' not registered",
            )

        return self._service.run_strategy(
            strategy=strategy,
            symbol=symbol,
            candles_by_timeframe=candles_by_timeframe,
            parameters=parameters,
            data_source=data_source,
        )

    def run_all_enabled(
        self,
        symbol: str,
        candles_by_timeframe: Dict[MarketTimeframe, List[OHLCBar]],
        parameters_map: Optional[Dict[str, StrategyParameters]] = None,
        data_source: DataSource = DataSource.SIMULATED,
    ) -> List[StrategyResult]:
        """Run all enabled strategies on a symbol/timeframe set.

        Each strategy is isolated — errors in one do not affect others.
        """
        results: List[StrategyResult] = []
        for name in self._registry.enabled_strategies():
            params = None
            if parameters_map and name in parameters_map:
                params = parameters_map[name]
            try:
                result = self.run_strategy(
                    strategy_name=name,
                    symbol=symbol,
                    candles_by_timeframe=candles_by_timeframe,
                    parameters=params,
                    data_source=data_source,
                )
                results.append(result)
            except Exception as exc:  # noqa: BLE001 — outer safety net
                self._logger.exception(
                    "Unexpected error running strategy %s: %s", name, exc
                )
                entry_tf = (
                    candles_by_timeframe.keys()[0]
                    if candles_by_timeframe
                    else MarketTimeframe.M1
                )
                results.append(
                    StrategyResult(
                        strategy_name=name,
                        symbol=symbol,
                        timeframe=entry_tf,
                        signals=[],
                        rejections=[],
                        market_regime=MarketRegime.UNKNOWN,
                        indicator_snapshots={},
                        error=f"Unexpected error: {exc}",
                    )
                )
        return results

    # ------------------------------------------------------------------
    # Conflict detection and aggregation
    # ------------------------------------------------------------------

    def detect_conflicts(
        self, results: List[StrategyResult]
    ) -> Dict[str, Any]:
        """Detect conflicting signals across strategy results.

        Returns a dict with:
            * has_conflicts: bool
            * conflicts: list of conflict descriptions
            * agreement: list of agreeing strategy groups
            * aggregated_direction: aggregated signal direction or None
        """
        return self._conflict_resolver.detect(results)

    def aggregate_signals(
        self,
        results: List[StrategyResult],
        policy: str = "report_conflicts",
    ) -> Dict[str, Any]:
        """Aggregate signals from multiple strategies.

        Policies:
            * "report_conflicts" — return all signals with conflict annotations
            * "consensus" — require all agreeing strategies for a direction
            * "majority" — direction with most supporting strategies
            * "unanimous" — only if all strategies agree
        """
        return self._conflict_resolver.aggregate(results, policy=policy)

    # ------------------------------------------------------------------
    # Signal lifecycle management
    # ------------------------------------------------------------------

    def clear_signal_history(self) -> None:
        """Clear the duplicate signal history (useful for testing)."""
        self._service.clear_signal_history()

    def filter_expired_signals(
        self,
        results: List[StrategyResult],
        now: Optional[datetime] = None,
    ) -> List[StrategyResult]:
        """Return results with expired signals removed."""
        check_time = now or datetime.now(timezone.utc)
        filtered: List[StrategyResult] = []
        for result in results:
            active = self._service.filter_expired_signals(
                result.signals, check_time
            )
            filtered.append(StrategyResult(
                strategy_name=result.strategy_name,
                symbol=result.symbol,
                timeframe=result.timeframe,
                signals=active,
                rejections=result.rejections,
                market_regime=result.market_regime,
                indicator_snapshots=result.indicator_snapshots,
                error=result.error,
                validation_passed=result.validation_passed,
            ))
        return filtered

    def filter_invalidated_signals(
        self,
        results: List[StrategyResult],
        current_price: Decimal,
    ) -> List[StrategyResult]:
        """Return results with invalidated signals removed."""
        filtered: List[StrategyResult] = []
        for result in results:
            active = self._service.filter_invalidated_signals(
                result.signals, current_price
            )
            filtered.append(StrategyResult(
                strategy_name=result.strategy_name,
                symbol=result.symbol,
                timeframe=result.timeframe,
                signals=active,
                rejections=result.rejections,
                market_regime=result.market_regime,
                indicator_snapshots=result.indicator_snapshots,
                error=result.error,
                validation_passed=result.validation_passed,
            ))
        return filtered

    # ------------------------------------------------------------------
    # Risk interface export (Phase 6 integration contract)
    # ------------------------------------------------------------------

    def export_risk_interface_signals(
        self,
        results: List[StrategyResult],
    ) -> List[RiskInterfaceSignal]:
        """Export all active signals to Phase 6 RiskInterfaceSignal format.

        This is the integration contract between Phase 5 (Strategy Engine)
        and Phase 6 (Risk Management Engine). Phase 5 produces signals;
        Phase 6 consumes them for risk evaluation, position sizing, and
        stop-loss/take-profit calculation. No order execution occurs at
        this boundary.
        """
        exported: List[RiskInterfaceSignal] = []
        for result in results:
            if result.error:
                continue
            for sig in result.signals:
                if not sig.is_actionable():
                    continue
                exported.append(self._service.to_risk_interface_signal(sig))
        return exported

    def get_signal_history_count(self) -> int:
        """Return the number of signal keys in the duplicate history."""
        return len(self._service._signal_history)

