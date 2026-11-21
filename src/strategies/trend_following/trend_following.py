"""Trend Following Strategy.

Identifies trend direction and strength using EMA, SMA, ADX, MACD, and RSI.
Generates LONG signals in uptrends with confirmation, SHORT signals in
downtrends with confirmation, and NONE when conditions are not met.

Trend identification:
    * Uptrend: price above EMA/SMA, EMA fast > EMA slow, ADX >= trend_threshold
    * Downtrend: price below EMA/SMA, EMA fast < EMA slow, ADX >= trend_threshold
    * Weak trend: ADX between ranging and trending thresholds
    * Strong trend: ADX >= strong_trend_threshold
    * Potential reversal: ADX declining from high levels + price/MACD divergence signals

Signal generation (never single-indicator):
    * LONG: uptrend confirmed AND (trend continuation OR pullback setup)
    * SHORT: downtrend confirmed AND (trend continuation OR pullback setup)
    * NONE: weak trend, ranging, or conflicting signals
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.indicators.base import IndicatorParameters, ReadinessStatus
from src.market_data.models import DataSource, MarketTimeframe, OHLCBar
from src.strategies.base import (
    MarketRegime,
    Signal,
    SignalDirection,
    SignalStatus,
    Strategy,
    StrategyResult,
)
from src.strategies.models import (
    ConfirmationCondition,
    ConfirmationRule,
    StrategyParameters,
)
from src.strategies.service import SignalService


@dataclass(frozen=True)
class TrendFollowingParameters:
    """Parameters for the Trend Following Strategy."""

    ema_fast: int = 9
    ema_slow: int = 21
    sma_period: int = 50
    adx_period: int = 14
    adx_trending_threshold: Decimal = Decimal("25")
    adx_strong_threshold: Decimal = Decimal("40")
    adx_ranging_threshold: Decimal = Decimal("20")
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    rsi_period: int = 14
    rsi_overbought: Decimal = Decimal("70")
    rsi_oversold: Decimal = Decimal("30")
    pullback_rsi_max_long: Decimal = Decimal("45")
    pullback_rsi_min_short: Decimal = Decimal("55")
    min_confirmations: int = 2
    max_signal_age_minutes: int = 60


class TrendFollowingStrategy(Strategy):
    """Trend following strategy using EMA, SMA, ADX, MACD, RSI."""

    name = "TrendFollowing"
    version = "1.0.0"

    def __init__(self) -> None:
        self._enabled = True
        self._params = TrendFollowingParameters()
        self._signal_service: Optional[SignalService] = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    @property
    def required_timeframes(self) -> List[MarketTimeframe]:
        return [MarketTimeframe.H1, MarketTimeframe.H4, MarketTimeframe.D1]

    @property
    def supported_instruments(self) -> Optional[List[str]]:
        return None  # All instruments

    @property
    def supported_regimes(self) -> List[MarketRegime]:
        return [MarketRegime.TRENDING, MarketRegime.TRANSITIONING]

    @property
    def default_parameters(self) -> IndicatorParameters:
        return IndicatorParameters(values={
            "ema_fast": self._params.ema_fast,
            "ema_slow": self._params.ema_slow,
            "sma_period": self._params.sma_period,
            "adx_period": self._params.adx_period,
            "adx_trending_threshold": float(self._params.adx_trending_threshold),
            "adx_strong_threshold": float(self._params.adx_strong_threshold),
            "adx_ranging_threshold": float(self._params.adx_ranging_threshold),
            "macd_fast": self._params.macd_fast,
            "macd_slow": self._params.macd_slow,
            "macd_signal": self._params.macd_signal,
            "rsi_period": self._params.rsi_period,
            "rsi_overbought": float(self._params.rsi_overbought),
            "rsi_oversold": float(self._params.rsi_oversold),
            "pullback_rsi_max_long": float(self._params.pullback_rsi_max_long),
            "pullback_rsi_min_short": float(self._params.pullback_rsi_min_short),
            "min_confirmations": self._params.min_confirmations,
            "max_signal_age_minutes": self._params.max_signal_age_minutes,
        })

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        values = dict(parameters.values)
        # Validate ranges
        ema_fast = int(values.get("ema_fast", self._params.ema_fast))
        ema_slow = int(values.get("ema_slow", self._params.ema_slow))
        if ema_fast >= ema_slow:
            raise ValueError("ema_fast must be < ema_slow")
        if ema_fast < 1 or ema_slow < 1:
            raise ValueError("EMA periods must be >= 1")
        sma_period = int(values.get("sma_period", self._params.sma_period))
        if sma_period < 1:
            raise ValueError("sma_period must be >= 1")
        adx_period = int(values.get("adx_period", self._params.adx_period))
        if adx_period < 1:
            raise ValueError("adx_period must be >= 1")
        return IndicatorParameters(values=values)

    def analyze(
        self,
        symbol: str,
        candles_by_timeframe: Dict[MarketTimeframe, List[OHLCBar]],
        indicator_engine: Any,
        parameters: Optional[IndicatorParameters] = None,
        data_source: DataSource = DataSource.SIMULATED,
    ) -> StrategyResult:
        """Analyze trend conditions and generate signals."""
        from src.strategies.base import SignalRejection

        if not self._enabled:
            entry_tf = self.required_timeframes[0]
            return StrategyResult(
                strategy_name=self.name,
                symbol=symbol,
                timeframe=entry_tf,
                signals=[],
                rejections=[
                    SignalRejection(
                        symbol=symbol,
                        timeframe=entry_tf,
                        strategy_name=self.name,
                        reason="Strategy is disabled",
                        data_source=data_source,
                        timestamp=datetime.now(timezone.utc),
                    )
                ],
                market_regime=MarketRegime.UNKNOWN,
                indicator_snapshots={},
                error="Strategy is disabled",
            )

        entry_tf = self.required_timeframes[0]
        entry_candles = candles_by_timeframe.get(entry_tf, [])
        confirmation_tfs = self.required_timeframes[1:]

        if not entry_candles:
            return StrategyResult(
                strategy_name=self.name,
                symbol=symbol,
                timeframe=entry_tf,
                signals=[],
                rejections=[
                    SignalRejection(
                        symbol=symbol,
                        timeframe=entry_tf,
                        strategy_name=self.name,
                        reason=f"No candles available for {entry_tf.value}",
                        data_source=data_source,
                        timestamp=datetime.now(timezone.utc),
                    )
                ],
                market_regime=MarketRegime.UNKNOWN,
                indicator_snapshots={},
            )

        # --- Calculate indicators on entry timeframe ---
        p = dict(parameters.values) if parameters else dict(self.default_parameters.values)
        ema_fast = int(p.get("ema_fast", 9))
        ema_slow = int(p.get("ema_slow", 21))
        sma_period = int(p.get("sma_period", 50))
        adx_period = int(p.get("adx_period", 14))
        adx_trending = Decimal(str(p.get("adx_trending_threshold", 25)))
        adx_strong = Decimal(str(p.get("adx_strong_threshold", 40)))
        adx_ranging = Decimal(str(p.get("adx_ranging_threshold", 20)))
        macd_fast = int(p.get("macd_fast", 12))
        macd_slow = int(p.get("macd_slow", 26))
        macd_signal = int(p.get("macd_signal", 9))
        rsi_period = int(p.get("rsi_period", 14))
        rsi_overbought = Decimal(str(p.get("rsi_overbought", 70)))
        rsi_oversold = Decimal(str(p.get("rsi_oversold", 30)))
        pullback_rsi_max_long = Decimal(str(p.get("pullback_rsi_max_long", 45)))
        pullback_rsi_min_short = Decimal(str(p.get("pullback_rsi_min_short", 55)))
        min_confirmations = int(p.get("min_confirmations", 2))

        indicator_results: Dict[str, Any] = {}
        try:
            ema_fast_result = indicator_engine.calculate(
                "EMA", symbol, entry_tf, entry_candles,
                parameters=IndicatorParameters(values={"periods": [ema_fast]}),
                data_source=data_source,
            )
            indicator_results["ema_fast"] = ema_fast_result
        except Exception as exc:
            return StrategyResult(
                strategy_name=self.name, symbol=symbol, timeframe=entry_tf,
                signals=[], rejections=[], market_regime=MarketRegime.UNKNOWN,
                indicator_snapshots={}, error=f"EMA fast calculation failed: {exc}",
            )

        try:
            ema_slow_result = indicator_engine.calculate(
                "EMA", symbol, entry_tf, entry_candles,
                parameters=IndicatorParameters(values={"periods": [ema_slow]}),
                data_source=data_source,
            )
            indicator_results["ema_slow"] = ema_slow_result
        except Exception as exc:
            return StrategyResult(
                strategy_name=self.name, symbol=symbol, timeframe=entry_tf,
                signals=[], rejections=[], market_regime=MarketRegime.UNKNOWN,
                indicator_snapshots={}, error=f"EMA slow calculation failed: {exc}",
            )

        try:
            sma_result = indicator_engine.calculate(
                "SMA", symbol, entry_tf, entry_candles,
                parameters=IndicatorParameters(values={"periods": [sma_period]}),
                data_source=data_source,
            )
            indicator_results["sma"] = sma_result
        except Exception as exc:
            return StrategyResult(
                strategy_name=self.name, symbol=symbol, timeframe=entry_tf,
                signals=[], rejections=[], market_regime=MarketRegime.UNKNOWN,
                indicator_snapshots={}, error=f"SMA calculation failed: {exc}",
            )

        try:
            adx_result = indicator_engine.calculate(
                "ADX", symbol, entry_tf, entry_candles,
                parameters=IndicatorParameters(values={"period": adx_period}),
                data_source=data_source,
            )
            indicator_results["adx"] = adx_result
        except Exception as exc:
            return StrategyResult(
                strategy_name=self.name, symbol=symbol, timeframe=entry_tf,
                signals=[], rejections=[], market_regime=MarketRegime.UNKNOWN,
                indicator_snapshots={}, error=f"ADX calculation failed: {exc}",
            )

        try:
            macd_result = indicator_engine.calculate(
                "MACD", symbol, entry_tf, entry_candles,
                parameters=IndicatorParameters(values={
                    "fast_period": macd_fast,
                    "slow_period": macd_slow,
                    "signal_period": macd_signal,
                }),
                data_source=data_source,
            )
            indicator_results["macd"] = macd_result
        except Exception as exc:
            return StrategyResult(
                strategy_name=self.name, symbol=symbol, timeframe=entry_tf,
                signals=[], rejections=[], market_regime=MarketRegime.UNKNOWN,
                indicator_snapshots={}, error=f"MACD calculation failed: {exc}",
            )

        try:
            rsi_result = indicator_engine.calculate(
                "RSI", symbol, entry_tf, entry_candles,
                parameters=IndicatorParameters(values={"period": rsi_period}),
                data_source=data_source,
            )
            indicator_results["rsi"] = rsi_result
        except Exception as exc:
            return StrategyResult(
                strategy_name=self.name, symbol=symbol, timeframe=entry_tf,
                signals=[], rejections=[], market_regime=MarketRegime.UNKNOWN,
                indicator_snapshots={}, error=f"RSI calculation failed: {exc}",
            )

        # --- Extract latest values ---
        closes = [c.close for c in entry_candles]
        current_close = closes[-1] if closes else None

        ema_fast_series = indicator_results["ema_fast"].values.get(f"ema_{ema_fast}", [])
        ema_slow_series = indicator_results["ema_slow"].values.get(f"ema_{ema_slow}", [])
        sma_series = indicator_results["sma"].values.get(f"sma_{sma_period}", [])
        adx_series = indicator_results["adx"].values.get("adx", [])
        plus_di_series = indicator_results["adx"].values.get("plus_di", [])
        minus_di_series = indicator_results["adx"].values.get("minus_di", [])
        macd_series = indicator_results["macd"].values.get("macd", [])
        signal_series = indicator_results["macd"].values.get("signal", [])
        hist_series = indicator_results["macd"].values.get("histogram", [])
        rsi_series = indicator_results["rsi"].values.get("rsi", [])

        def last(series: List[Any]) -> Any:
            return series[-1] if series else None

        ema_fast_val = last(ema_fast_series)
        ema_slow_val = last(ema_slow_series)
        sma_val = last(sma_series)
        adx_val = last(adx_series)
        plus_di_val = last(plus_di_series)
        minus_di_val = last(minus_di_series)
        macd_val = last(macd_series)
        signal_val = last(signal_series)
        hist_val = last(hist_series)
        rsi_val = last(rsi_series)

        # Previous values for crossover detection
        prev_macd = macd_series[-2] if len(macd_series) >= 2 else None
        prev_signal = signal_series[-2] if len(signal_series) >= 2 else None
        prev_rsi = rsi_series[-2] if len(rsi_series) >= 2 else None

        # --- Trend determination ---
        is_uptrend = False
        is_downtrend = False
        is_weak_trend = False
        is_strong_trend = False
        trend_strength = "none"
        trend_conditions: List[str] = []

        # EMA alignment
        ema_bullish = (
            ema_fast_val is not None and ema_slow_val is not None
            and ema_fast_val > ema_slow_val
        )
        ema_bearish = (
            ema_fast_val is not None and ema_slow_val is not None
            and ema_fast_val < ema_slow_val
        )

        # Price vs SMA
        price_above_sma = (
            current_close is not None and sma_val is not None
            and current_close > sma_val
        )
        price_below_sma = (
            current_close is not None and sma_val is not None
            and current_close < sma_val
        )

        # ADX strength
        adx_strong_trend = adx_val is not None and adx_val >= adx_strong
        adx_trending_enough = adx_val is not None and adx_val >= adx_trending
        adx_ranging_enough = adx_val is not None and adx_val < adx_ranging

        if ema_bullish and price_above_sma and adx_trending_enough:
            is_uptrend = True
            trend_strength = "strong" if adx_strong_trend else "moderate"
            trend_conditions.append(
                f"EMA{ema_fast} > EMA{ema_slow}, price > SMA{sma_period}, ADX >= {adx_trending}"
            )
        elif ema_bearish and price_below_sma and adx_trending_enough:
            is_downtrend = True
            trend_strength = "strong" if adx_strong_trend else "moderate"
            trend_conditions.append(
                f"EMA{ema_fast} < EMA{ema_slow}, price < SMA{sma_period}, ADX >= {adx_trending}"
            )
        elif adx_val is not None and adx_val >= adx_ranging:
            is_weak_trend = True
            trend_strength = "weak"
            trend_conditions.append(f"ADX {adx_val} in weak trend zone")
        elif adx_ranging_enough:
            trend_strength = "ranging"
            trend_conditions.append(f"ADX {adx_val} below ranging threshold")

        if adx_strong_trend:
            is_strong_trend = True

        # --- Signal generation ---
        signals: List[Signal] = []
        rejections: List[SignalRejection] = []
        confirmation_conditions: List[str] = []
        explanation_parts: List[str] = list(trend_conditions)

        # Check if trend is supported by current regime
        direction: Optional[SignalDirection] = None

        if is_uptrend:
            # Check for LONG setup: trend continuation or pullback
            trend_continuation = (
                ema_bullish
                and price_above_sma
                and (macd_val is not None and macd_val > Decimal("0"))
                and (rsi_val is not None and rsi_val > Decimal("50"))
            )
            pullback_setup = (
                ema_bullish
                and price_above_sma
                and (rsi_val is not None and rsi_val <= pullback_rsi_max_long)
                and (rsi_val is not None and rsi_val > rsi_oversold)
                and (macd_val is not None and hist_val is not None and hist_val > Decimal("0"))
            )

            if trend_continuation:
                direction = SignalDirection.LONG
                confirmation_conditions.append("Trend continuation: EMA bullish, price > SMA, MACD > 0, RSI > 50")
                explanation_parts.append("LONG: trend continuation confirmed")
            elif pullback_setup:
                direction = SignalDirection.LONG
                confirmation_conditions.append("Pullback setup: EMA bullish, price > SMA, RSI oversold but recovering, MACD histogram positive")
                explanation_parts.append("LONG: pullback setup in uptrend")
            else:
                explanation_parts.append("Uptrend detected but entry conditions not met")

        elif is_downtrend:
            # Check for SHORT setup: trend continuation or pullback
            trend_continuation = (
                ema_bearish
                and price_below_sma
                and (macd_val is not None and macd_val < Decimal("0"))
                and (rsi_val is not None and rsi_val < Decimal("50"))
            )
            pullback_setup = (
                ema_bearish
                and price_below_sma
                and (rsi_val is not None and rsi_val >= pullback_rsi_min_short)
                and (rsi_val is not None and rsi_val < rsi_overbought)
                and (macd_val is not None and hist_val is not None and hist_val < Decimal("0"))
            )

            if trend_continuation:
                direction = SignalDirection.SHORT
                confirmation_conditions.append("Trend continuation: EMA bearish, price < SMA, MACD < 0, RSI < 50")
                explanation_parts.append("SHORT: trend continuation confirmed")
            elif pullback_setup:
                direction = SignalDirection.SHORT
                confirmation_conditions.append("Pullback setup: EMA bearish, price < SMA, RSI overbought but declining, MACD histogram negative")
                explanation_parts.append("SHORT: pullback setup in downtrend")
            else:
                explanation_parts.append("Downtrend detected but entry conditions not met")

        # --- Confirmation count check ---
        confirmations_met = 0
        if ema_bullish or ema_bearish:
            confirmations_met += 1
        if adx_trending_enough:
            confirmations_met += 1
        if macd_val is not None and signal_val is not None:
            if (direction == SignalDirection.LONG and macd_val > signal_val) or \
               (direction == SignalDirection.SHORT and macd_val < signal_val):
                confirmations_met += 1
        if rsi_val is not None:
            if (direction == SignalDirection.LONG and rsi_val > Decimal("50")) or \
               (direction == SignalDirection.SHORT and rsi_val < Decimal("50")):
                confirmations_met += 1

        if direction is not None and confirmations_met < min_confirmations:
            direction = None
            explanation_parts.append(
                f"Insufficient confirmations: {confirmations_met}/{min_confirmations}"
            )

        # --- Build signal ---
        now = datetime.now(timezone.utc)
        last_candle_ts = entry_candles[-1].timestamp if entry_candles else now

        if direction is not None:
            # Technical invalidation: opposite EMA crossover level
            invalidation: Optional[Decimal] = None
            if direction == SignalDirection.LONG:
                invalidation = ema_slow_val  # Below slow EMA invalidates uptrend
            elif direction == SignalDirection.SHORT:
                invalidation = ema_slow_val  # Above slow EMA invalidates downtrend

            signals.append(Signal(
                signal_id="",  # Will be set by SignalService
                strategy_name=self.name,
                strategy_version=self.version,
                symbol=symbol,
                instrument_type="forex",
                direction=direction,
                status=SignalStatus.ACTIVE,
                entry_timeframe=entry_tf,
                confirmation_timeframes=confirmation_tfs,
                signal_timestamp=now,
                market_data_timestamp=last_candle_ts,
                reference_price=current_close,
                technical_invalidation=invalidation,
                parameters=IndicatorParameters(values=dict(p)),
                indicator_snapshot={
                    f"ema_{ema_fast}": ema_fast_series,
                    f"ema_{ema_slow}": ema_slow_series,
                    f"sma_{sma_period}": sma_series,
                    "adx": adx_series,
                    "plus_di": plus_di_series,
                    "minus_di": minus_di_series,
                    "macd": macd_series,
                    "macd_signal": signal_series,
                    "macd_histogram": hist_series,
                    "rsi": rsi_series,
                },
                market_regime=MarketRegime.TRENDING if is_strong_trend else MarketRegime.TRANSITIONING,
                confirmation_conditions=confirmation_conditions,
                explanation=". ".join(explanation_parts) + ".",
                expiry_conditions=[
                    f"Trend reversal: EMA{ema_fast} crosses opposite EMA{ema_slow}",
                    f"ADX falls below {adx_ranging}",
                    f"Signal age exceeds {p.get('max_signal_age_minutes', 60)} minutes",
                ],
                data_source=data_source,
                strategy_validity_state="valid" if self._enabled else "disabled",
                metadata={
                    "trend_strength": trend_strength,
                    "confirmations_met": confirmations_met,
                    "min_confirmations": min_confirmations,
                    "ema_fast": float(ema_fast_val) if ema_fast_val is not None else None,
                    "ema_slow": float(ema_slow_val) if ema_slow_val is not None else None,
                    "adx": float(adx_val) if adx_val is not None else None,
                    "rsi": float(rsi_val) if rsi_val is not None else None,
                    "macd": float(macd_val) if macd_val is not None else None,
                },
            ))
        else:
            rejections.append(SignalRejection(
                symbol=symbol,
                timeframe=entry_tf,
                strategy_name=self.name,
                reason="; ".join(explanation_parts) if explanation_parts else "No trend conditions met",
                data_source=data_source,
                timestamp=now,
            ))

        return StrategyResult(
            strategy_name=self.name,
            symbol=symbol,
            timeframe=entry_tf,
            signals=signals,
            rejections=rejections,
            market_regime=MarketRegime.TRENDING if is_strong_trend else MarketRegime.TRANSITIONING,
            indicator_snapshots={
                "ema_fast": IndicatorParameters(values={"period": ema_fast}),
                "ema_slow": IndicatorParameters(values={"period": ema_slow}),
                "sma": IndicatorParameters(values={"period": sma_period}),
                "adx": IndicatorParameters(values={"period": adx_period}),
                "macd": IndicatorParameters(values={
                    "fast_period": macd_fast, "slow_period": macd_slow, "signal_period": macd_signal
                }),
                "rsi": IndicatorParameters(values={"period": rsi_period}),
            },
        )
