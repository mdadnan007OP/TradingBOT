"""SignalService — bridge between strategies and the Phase 4 Indicator Engine.

Orchestrates indicator calculation for multiple timeframes and passes results
to strategy analysis methods. Stateless and source-aware.

Adds signal lifecycle management:
    * Validation of candles (count, OHLC validity, completeness, freshness).
    * Duplicate signal prevention (same strategy + symbol + timeframe + candle).
    * Signal expiration (signal_valid_until enforcement).
    * Signal invalidation (price crossing technical_invalidation).
    * Risk interface export for Phase 6 integration.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

from src.indicators.base import IndicatorParameters, IndicatorResult, ReadinessStatus
from src.indicators.service import IndicatorEngine
from src.market_data.models import DataSource, MarketTimeframe, OHLCBar
from src.strategies.base import (
    MarketRegime,
    Signal,
    SignalDirection,
    SignalRejection,
    SignalStatus,
    Strategy,
    StrategyResult,
)
from src.strategies.market_regime import MarketRegimeDetector, MarketRegimeResult
from src.strategies.models import (
    RiskInterfaceSignal,
    SignalValidationResult,
    StrategyParameters,
    compute_config_fingerprint,
)


class SignalService:
    """Orchestrates indicator calculation and strategy analysis.

    Responsibilities:
        * Retrieve indicator values for multiple timeframes.
        * Detect market regime per symbol/timeframe.
        * Validate signal prerequisites (candles, OHLC, completeness, freshness).
        * Delegate to strategy.analyze() with indicator results.
        * Return StrategyResult objects with signals and rejections.
        * Track signal history for duplicate detection.
        * Export signals to the Phase 6 risk interface format.
    """

    def __init__(
        self,
        indicator_engine: IndicatorEngine,
        market_regime_detector: Optional[MarketRegimeDetector] = None,
        max_signal_age_minutes: int = 60,
    ) -> None:
        self._indicator_engine = indicator_engine
        self._regime_detector = market_regime_detector or MarketRegimeDetector()
        self._max_signal_age_minutes = max_signal_age_minutes
        # Signal history for duplicate detection: set of duplicate keys already seen
        self._signal_history: Set[str] = set()

    # ------------------------------------------------------------------
    # Indicator retrieval helpers
    # ------------------------------------------------------------------

    def get_indicator_result(
        self,
        name: str,
        symbol: str,
        timeframe: MarketTimeframe,
        candles: List[OHLCBar],
        parameters: Optional[IndicatorParameters] = None,
        data_source: DataSource = DataSource.SIMULATED,
    ) -> IndicatorResult:
        """Calculate an indicator for a symbol/timeframe."""
        return self._indicator_engine.calculate(
            name=name,
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            parameters=parameters,
            data_source=data_source,
        )

    def get_indicator_snapshot(
        self,
        indicator_names: List[str],
        symbol: str,
        timeframe: MarketTimeframe,
        candles: List[OHLCBar],
        parameters_map: Optional[Dict[str, IndicatorParameters]] = None,
        data_source: DataSource = DataSource.SIMULATED,
    ) -> Dict[str, IndicatorResult]:
        """Calculate multiple indicators and return results keyed by name."""
        results: Dict[str, IndicatorResult] = {}
        for name in indicator_names:
            params = None
            if parameters_map and name in parameters_map:
                params = parameters_map[name]
            results[name] = self.get_indicator_result(
                name, symbol, timeframe, candles,
                parameters=params, data_source=data_source,
            )
        return results

    # ------------------------------------------------------------------
    # Market regime
    # ------------------------------------------------------------------

    def detect_regime(
        self,
        symbol: str,
        candles: List[OHLCBar],
        timeframe: MarketTimeframe,
        parameters: Optional[Dict[str, Any]] = None,
        data_source: DataSource = DataSource.SIMULATED,
    ) -> MarketRegimeResult:
        """Detect market regime for a symbol/timeframe."""
        return self._regime_detector.detect(
            symbol=symbol,
            candles=candles,
            indicator_engine=self._indicator_engine,
            parameters=parameters,
            data_source=data_source.value if hasattr(data_source, "value") else str(data_source),
        )

    # ------------------------------------------------------------------
    # Signal validation
    # ------------------------------------------------------------------

    def validate_signal_prerequisites(
        self,
        symbol: str,
        candles: List[OHLCBar],
        timeframe: MarketTimeframe,
        required_indicators: Optional[List[str]] = None,
        data_source: DataSource = DataSource.SIMULATED,
        min_candles: int = 2,
        max_staleness_minutes: Optional[int] = None,
    ) -> SignalValidationResult:
        """Validate that candles and indicators are sufficient for signal generation.

        Checks:
            * At least min_candles available.
            * All candles have valid OHLC (high >= low, high >= open/close,
              low <= open/close).
            * All candles are complete (not forming).
            * Data is not stale (most recent candle within max_staleness_minutes).
            * Required indicators are available and ready.

        Returns a SignalValidationResult with pass/fail and details.
        """
        now = datetime.now(timezone.utc)
        candle_count = len(candles)
        missing_indicators: List[str] = []
        stale_seconds: Optional[int] = None

        # 1. Sufficient candles
        if candle_count < min_candles:
            return SignalValidationResult(
                valid=False,
                category="insufficient_data",
                reason=(
                    f"Insufficient candles: {candle_count} available, "
                    f"need at least {min_candles}"
                ),
                candle_count=candle_count,
                missing_indicators=missing_indicators,
                stale_data_seconds=stale_seconds,
            )

        # 2. Valid OHLC
        for i, c in enumerate(candles):
            if c.high < c.low:
                return SignalValidationResult(
                    valid=False,
                    category="invalid_ohlc",
                    reason=f"Candle {i}: high ({c.high}) < low ({c.low})",
                    candle_count=candle_count,
                    missing_indicators=missing_indicators,
                    stale_data_seconds=stale_seconds,
                )
            if c.high < c.open or c.high < c.close:
                return SignalValidationResult(
                    valid=False,
                    category="invalid_ohlc",
                    reason=f"Candle {i}: high ({c.high}) below open or close",
                    candle_count=candle_count,
                    missing_indicators=missing_indicators,
                    stale_data_seconds=stale_seconds,
                )
            if c.low > c.open or c.low > c.close:
                return SignalValidationResult(
                    valid=False,
                    category="invalid_ohlc",
                    reason=f"Candle {i}: low ({c.low}) above open or close",
                    candle_count=candle_count,
                    missing_indicators=missing_indicators,
                    stale_data_seconds=stale_seconds,
                )

        # 3. Completed candles only
        incomplete_count = sum(1 for c in candles if not c.is_complete)
        if incomplete_count > 0:
            return SignalValidationResult(
                valid=False,
                category="incomplete_candle",
                reason=(
                    f"{incomplete_count} of {candle_count} candles are incomplete "
                    f"(forming). Use allow_incomplete opt-in if required."
                ),
                candle_count=candle_count,
                missing_indicators=missing_indicators,
                stale_data_seconds=stale_seconds,
            )

        # 4. Data freshness
        if candles and max_staleness_minutes is not None:
            latest_candle = max(candles, key=lambda c: c.timestamp)
            stale_seconds = int((now - latest_candle.timestamp).total_seconds())
            if stale_seconds > max_staleness_minutes * 60:
                return SignalValidationResult(
                    valid=False,
                    category="stale_data",
                    reason=(
                        f"Market data is {stale_seconds}s old, exceeds "
                        f"max staleness of {max_staleness_minutes * 60}s"
                    ),
                    candle_count=candle_count,
                    missing_indicators=missing_indicators,
                    stale_data_seconds=stale_seconds,
                )

        # 5. Required indicators available and ready
        if required_indicators:
            for ind_name in required_indicators:
                try:
                    result = self.get_indicator_result(
                        ind_name, symbol, timeframe, candles,
                        data_source=data_source,
                    )
                    readiness = result.readiness
                    readiness_str = (
                        readiness.value if hasattr(readiness, "value") else str(readiness)
                    )
                    if readiness_str not in ("ready", "READY"):
                        missing_indicators.append(ind_name)
                except Exception:  # noqa: BLE001
                    missing_indicators.append(ind_name)

        if missing_indicators:
            return SignalValidationResult(
                valid=False,
                category="unavailable_indicator",
                reason=(
                    f"Required indicators unavailable or not ready: "
                    f"{', '.join(missing_indicators)}"
                ),
                candle_count=candle_count,
                missing_indicators=missing_indicators,
                stale_data_seconds=stale_seconds,
            )

        return SignalValidationResult(
            valid=True,
            category=None,
            reason=None,
            candle_count=candle_count,
            missing_indicators=[],
            stale_data_seconds=stale_seconds,
        )

    def is_duplicate_signal(
        self,
        strategy_name: str,
        symbol: str,
        timeframe: MarketTimeframe,
        market_data_timestamp: datetime,
    ) -> bool:
        """Check if a signal with the same key was already generated.

        Duplicate key = strategy_name | symbol | timeframe | market_data_timestamp.
        """
        key = "|".join([
            strategy_name,
            symbol,
            timeframe.value,
            str(market_data_timestamp),
        ])
        return key in self._signal_history

    def record_signal(
        self,
        strategy_name: str,
        symbol: str,
        timeframe: MarketTimeframe,
        market_data_timestamp: datetime,
    ) -> None:
        """Record a signal key to prevent future duplicates."""
        key = "|".join([
            strategy_name,
            symbol,
            timeframe.value,
            str(market_data_timestamp),
        ])
        self._signal_history.add(key)

    def clear_signal_history(self) -> None:
        """Clear the duplicate signal history (useful for testing)."""
        self._signal_history.clear()

    # ------------------------------------------------------------------
    # Signal expiration and invalidation
    # ------------------------------------------------------------------

    def compute_signal_valid_until(
        self,
        signal_timestamp: datetime,
        max_age_minutes: Optional[int] = None,
    ) -> Optional[datetime]:
        """Compute the expiry timestamp for a signal.

        Returns None if max_age_minutes is None (no expiry).
        """
        if max_age_minutes is None:
            return None
        return signal_timestamp + timedelta(minutes=max_age_minutes)

    def filter_expired_signals(
        self,
        signals: List[Signal],
        now: Optional[datetime] = None,
    ) -> List[Signal]:
        """Return signals that are not expired."""
        check_time = now or datetime.now(timezone.utc)
        return [s for s in signals if not s.is_expired(check_time)]

    def filter_invalidated_signals(
        self,
        signals: List[Signal],
        current_price: Decimal,
    ) -> List[Signal]:
        """Return signals whose technical invalidation level has not been hit."""
        return [s for s in signals if not s.is_invalidated(current_price)]

    # ------------------------------------------------------------------
    # Market regime
    # ------------------------------------------------------------------

    def detect_regime(
        self,
        symbol: str,
        candles: List[OHLCBar],
        timeframe: MarketTimeframe,
        parameters: Optional[Dict[str, Any]] = None,
        data_source: DataSource = DataSource.SIMULATED,
    ) -> MarketRegimeResult:
        """Detect market regime for a symbol/timeframe."""
        return self._regime_detector.detect(
            symbol=symbol,
            candles=candles,
            indicator_engine=self._indicator_engine,
            parameters=parameters,
            data_source=data_source.value if hasattr(data_source, "value") else str(data_source),
        )

    # ------------------------------------------------------------------
    # Strategy execution
    # ------------------------------------------------------------------

    def run_strategy(
        self,
        strategy: Strategy,
        symbol: str,
        candles_by_timeframe: Dict[MarketTimeframe, List[OHLCBar]],
        parameters: Optional[StrategyParameters] = None,
        data_source: DataSource = DataSource.SIMULATED,
    ) -> StrategyResult:
        """Run a single strategy on a symbol across multiple timeframes.

        If the strategy errors, returns a StrategyResult with the error
        recorded (fault isolation).
        """
        if not strategy.enabled:
            return StrategyResult(
                strategy_name=strategy.name,
                symbol=symbol,
                timeframe=candles_by_timeframe.keys()[
                    0
                ] if candles_by_timeframe else MarketTimeframe.M1,
                signals=[],
                rejections=[],
                market_regime=MarketRegime.UNKNOWN,
                indicator_snapshots={},
                error="Strategy is disabled",
                validation_passed=False,
            )

        entry_tf = strategy.required_timeframes[0] if strategy.required_timeframes else MarketTimeframe.M1
        entry_candles = candles_by_timeframe.get(entry_tf, [])

        # Validate prerequisites before analysis
        validation = self.validate_signal_prerequisites(
            symbol=symbol,
            candles=entry_candles,
            timeframe=entry_tf,
            data_source=data_source,
            min_candles=2,
        )
        if not validation.valid:
            return StrategyResult(
                strategy_name=strategy.name,
                symbol=symbol,
                timeframe=entry_tf,
                signals=[],
                rejections=[
                    SignalRejection(
                        symbol=symbol,
                        timeframe=entry_tf,
                        strategy_name=strategy.name,
                        reason=validation.reason or "Validation failed",
                        category=validation.category or "unknown",
                        data_source=data_source,
                        timestamp=datetime.now(timezone.utc),
                        candle_count=validation.candle_count,
                        missing_indicators=validation.missing_indicators,
                    )
                ],
                market_regime=MarketRegime.UNKNOWN,
                indicator_snapshots={},
                validation_passed=False,
            )

        # Detect market regime on the entry timeframe
        regime_result = self.detect_regime(
            symbol, entry_candles, entry_tf,
            parameters=parameters.values if parameters else None,
            data_source=data_source,
        )

        regime_enum = MarketRegime.UNKNOWN
        try:
            regime_enum = MarketRegime(regime_result.regime)
        except ValueError:
            regime_enum = MarketRegime.UNKNOWN

        # Skip if regime not supported by strategy
        if regime_enum not in strategy.supported_regimes:
            return StrategyResult(
                strategy_name=strategy.name,
                symbol=symbol,
                timeframe=entry_tf,
                signals=[],
                rejections=[
                    SignalRejection(
                        symbol=symbol,
                        timeframe=entry_tf,
                        strategy_name=strategy.name,
                        reason=(
                            f"Market regime '{regime_result.regime}' not supported "
                            f"by strategy (supported: "
                            f"{[r.value for r in strategy.supported_regimes]})"
                        ),
                        category="regime_unsupported",
                        data_source=data_source,
                        timestamp=datetime.now(timezone.utc),
                    )
                ],
                market_regime=regime_enum,
                indicator_snapshots={},
                validation_passed=True,
            )

        # Validate parameters
        params = parameters
        if params is None:
            params = StrategyParameters(
                values=dict(strategy.default_parameters.values),
                entry_timeframe=entry_tf,
                confirmation_timeframes=list(strategy.required_timeframes[1:]),
            )
        else:
            params = StrategyParameters(
                values=strategy.validate_parameters(
                    IndicatorParameters(values=dict(params.values))
                ).values,
                confirmation_rules=params.confirmation_rules,
                entry_timeframe=params.entry_timeframe or entry_tf,
                confirmation_timeframes=params.confirmation_timeframes or list(strategy.required_timeframes[1:]),
                min_confirmations=params.min_confirmations,
                max_signal_age_minutes=params.max_signal_age_minutes,
                technical_invalidation_buffer=params.technical_invalidation_buffer,
            )

        # Delegate to strategy
        try:
            result = strategy.analyze(
                symbol=symbol,
                candles_by_timeframe=candles_by_timeframe,
                indicator_engine=self._indicator_engine,
                parameters=params.to_indicator_parameters(),
                data_source=data_source,
            )
            # Ensure regime is set
            if result.market_regime == MarketRegime.UNKNOWN:
                result = StrategyResult(
                    strategy_name=result.strategy_name,
                    symbol=result.symbol,
                    timeframe=result.timeframe,
                    signals=result.signals,
                    rejections=result.rejections,
                    market_regime=regime_enum,
                    indicator_snapshots=result.indicator_snapshots,
                    error=result.error,
                    validation_passed=True,
                )

            # Apply duplicate detection, expiration, and invalidation
            result = self._post_process_signals(result, params)

            return result
        except Exception as exc:  # noqa: BLE001 — fault isolation
            return StrategyResult(
                strategy_name=strategy.name,
                symbol=symbol,
                timeframe=entry_tf,
                signals=[],
                rejections=[
                    SignalRejection(
                        symbol=symbol,
                        timeframe=entry_tf,
                        strategy_name=strategy.name,
                        reason=f"Strategy error: {exc}",
                        category="strategy_error",
                        data_source=data_source,
                        timestamp=datetime.now(timezone.utc),
                    )
                ],
                market_regime=regime_enum,
                indicator_snapshots={},
                validation_passed=False,
                error=str(exc),
            )

    def _post_process_signals(
        self,
        result: StrategyResult,
        parameters: StrategyParameters,
    ) -> StrategyResult:
        """Apply duplicate detection, expiration, and config fingerprint.

        * Removes duplicate signals (same strategy + symbol + timeframe + candle).
        * Sets signal_valid_until based on max_signal_age_minutes.
        * Adds config_fingerprint to each signal.
        * Records signal keys in history for future duplicate prevention.
        """
        max_age = parameters.max_signal_age_minutes
        now = datetime.now(timezone.utc)
        fingerprint = compute_config_fingerprint(dict(parameters.values))

        filtered_signals: List[Signal] = []
        for sig in result.signals:
            # Duplicate check
            if self.is_duplicate_signal(
                sig.strategy_name, sig.symbol, sig.entry_timeframe,
                sig.market_data_timestamp,
            ):
                continue
            # Record this signal to prevent future duplicates
            self.record_signal(
                sig.strategy_name, sig.symbol, sig.entry_timeframe,
                sig.market_data_timestamp,
            )

            # Apply expiry
            valid_until = self.compute_signal_valid_until(
                sig.signal_timestamp, max_age
            )

            # Build new signal with lifecycle fields
            filtered_signals.append(Signal(
                signal_id=sig.signal_id,
                strategy_name=sig.strategy_name,
                strategy_version=sig.strategy_version,
                config_fingerprint=fingerprint,
                symbol=sig.symbol,
                instrument_type=sig.instrument_type,
                direction=sig.direction,
                status=sig.status,
                entry_timeframe=sig.entry_timeframe,
                confirmation_timeframes=sig.confirmation_timeframes,
                signal_timestamp=sig.signal_timestamp,
                signal_valid_until=valid_until,
                market_data_timestamp=sig.market_data_timestamp,
                reference_price=sig.reference_price,
                technical_invalidation=sig.technical_invalidation,
                parameters=sig.parameters,
                indicator_snapshot=sig.indicator_snapshot,
                market_regime=sig.market_regime,
                confirmation_conditions=sig.confirmation_conditions,
                failed_conditions=getattr(sig, "failed_conditions", []),
                explanation=sig.explanation,
                expiry_conditions=sig.expiry_conditions,
                data_source=sig.data_source,
                strategy_validity_state=sig.strategy_validity_state,
                metadata=sig.metadata,
            ))

        # Filter expired signals
        filtered_signals = self.filter_expired_signals(filtered_signals, now)

        return StrategyResult(
            strategy_name=result.strategy_name,
            symbol=result.symbol,
            timeframe=result.timeframe,
            signals=filtered_signals,
            rejections=result.rejections,
            market_regime=result.market_regime,
            indicator_snapshots=result.indicator_snapshots,
            error=result.error,
            validation_passed=result.validation_passed,
        )

    # ------------------------------------------------------------------
    # Risk interface export
    # ------------------------------------------------------------------

    def to_risk_interface_signal(
        self,
        signal: Signal,
    ) -> RiskInterfaceSignal:
        """Convert a Signal to the Phase 6 RiskInterfaceSignal format.

        This is the integration contract between Phase 5 (Strategy Engine)
        and Phase 6 (Risk Management Engine). Phase 5 produces signals;
        Phase 6 consumes them for risk evaluation, position sizing, and
        stop-loss/take-profit calculation.
        """
        return RiskInterfaceSignal(
            signal_id=signal.signal_id,
            strategy_name=signal.strategy_name,
            strategy_version=signal.strategy_version,
            config_fingerprint=signal.config_fingerprint,
            symbol=signal.symbol,
            instrument_type=signal.instrument_type,
            direction=signal.direction.value,
            signal_timestamp=signal.signal_timestamp,
            signal_valid_until=signal.signal_valid_until,
            market_data_timestamp=signal.market_data_timestamp,
            reference_price=signal.reference_price,
            technical_invalidation=signal.technical_invalidation,
            market_regime=signal.market_regime.value,
            confirmation_conditions=signal.confirmation_conditions,
            failed_conditions=getattr(signal, "failed_conditions", []),
            explanation=signal.explanation,
            expiry_conditions=signal.expiry_conditions,
            data_source=signal.data_source.value
            if hasattr(signal.data_source, "value")
            else str(signal.data_source),
            indicator_snapshot=signal.indicator_snapshot,
            parameters=dict(signal.parameters.values),
            entry_timeframe=signal.entry_timeframe,
            confirmation_timeframes=signal.confirmation_timeframes,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_rejection(
        symbol: str,
        timeframe: MarketTimeframe,
        strategy_name: str,
        reason: str,
        data_source: DataSource,
        category: str = "unknown",
        candle_count: Optional[int] = None,
        missing_indicators: Optional[List[str]] = None,
    ) -> SignalRejection:
        return SignalRejection(
            symbol=symbol,
            timeframe=timeframe,
            strategy_name=strategy_name,
            reason=reason,
            category=category,
            data_source=data_source,
            timestamp=datetime.now(timezone.utc),
            candle_count=candle_count,
            missing_indicators=missing_indicators or [],
        )

    def build_signal(
        self,
        strategy: Strategy,
        symbol: str,
        direction: SignalDirection,
        entry_timeframe: MarketTimeframe,
        confirmation_timeframes: List[MarketTimeframe],
        signal_timestamp: datetime,
        market_data_timestamp: datetime,
        reference_price: Optional[Decimal],
        technical_invalidation: Optional[Decimal],
        parameters: StrategyParameters,
        indicator_snapshot: Dict[str, List[Optional[Decimal]]],
        market_regime: MarketRegime,
        confirmation_conditions: List[str],
        explanation: str,
        expiry_conditions: List[str],
        data_source: DataSource,
        signal_id: Optional[str] = None,
        strategy_version: Optional[str] = None,
        status: SignalStatus = SignalStatus.ACTIVE,
        metadata: Optional[Dict[str, Any]] = None,
        failed_conditions: Optional[List[str]] = None,
    ) -> Signal:
        """Construct a standardized Signal object with lifecycle fields."""
        import uuid

        fingerprint = compute_config_fingerprint(dict(parameters.values))
        max_age = parameters.max_signal_age_minutes
        valid_until = self.compute_signal_valid_until(signal_timestamp, max_age)

        return Signal(
            signal_id=signal_id or str(uuid.uuid4()),
            strategy_name=strategy.name,
            strategy_version=strategy_version or strategy.version,
            config_fingerprint=fingerprint,
            symbol=symbol,
            instrument_type="forex",  # Default; strategies may override
            direction=direction,
            status=status,
            entry_timeframe=entry_timeframe,
            confirmation_timeframes=confirmation_timeframes,
            signal_timestamp=signal_timestamp,
            signal_valid_until=valid_until,
            market_data_timestamp=market_data_timestamp,
            reference_price=reference_price,
            technical_invalidation=technical_invalidation,
            parameters=parameters.to_indicator_parameters(),
            indicator_snapshot=indicator_snapshot,
            market_regime=market_regime,
            confirmation_conditions=confirmation_conditions,
            failed_conditions=failed_conditions or [],
            explanation=explanation,
            expiry_conditions=expiry_conditions,
            data_source=data_source,
            strategy_validity_state="valid" if strategy.enabled else "disabled",
            metadata=metadata or {},
        )
