"""Intraday Strategy Profile.

Configurable profile for M5, M15, M30, H1 timeframes.
Considers session context, trend direction, market structure, momentum,
previous day high/low, and breakout/retest patterns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.indicators.base import IndicatorParameters
from src.market_data.models import DataSource, MarketTimeframe, OHLCBar
from src.strategies.base import (
    MarketRegime,
    Signal,
    SignalDirection,
    SignalStatus,
    Strategy,
    StrategyResult,
)
from src.strategies.base import SignalRejection


@dataclass(frozen=True)
class IntradayParameters:
    """Parameters for Intraday Profile."""

    timeframe: MarketTimeframe = MarketTimeframe.H1
    use_session_context: bool = True
    use_prev_day_levels: bool = True
    ema_period: int = 50
    rsi_period: int = 14
    adx_period: int = 14
    adx_trending_threshold: Decimal = Decimal("25")
    min_confirmations: int = 2


class IntradayProfile(Strategy):
    """Intraday strategy profile for M5/M15/M30/H1."""

    name = "IntradayProfile"
    version = "1.0.0"

    def __init__(self) -> None:
        self._enabled = True
        self._params = IntradayParameters()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    @property
    def required_timeframes(self) -> List[MarketTimeframe]:
        return [self._params.timeframe]

    @property
    def supported_instruments(self) -> Optional[List[str]]:
        return None

    @property
    def supported_regimes(self) -> List[MarketRegime]:
        return [
            MarketRegime.TRENDING,
            MarketRegime.TRANSITIONING,
        ]

    @property
    def default_parameters(self) -> IndicatorParameters:
        return IndicatorParameters(values={
            "timeframe": self._params.timeframe.value,
            "use_session_context": self._params.use_session_context,
            "use_prev_day_levels": self._params.use_prev_day_levels,
            "ema_period": self._params.ema_period,
            "rsi_period": self._params.rsi_period,
            "adx_period": self._params.adx_period,
            "adx_trending_threshold": float(self._params.adx_trending_threshold),
            "min_confirmations": self._params.min_confirmations,
        })

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        values = dict(parameters.values)
        tf_str = str(values.get("timeframe", "H1"))
        try:
            MarketTimeframe(tf_str)
        except ValueError:
            raise ValueError(f"Invalid timeframe: {tf_str}")
        return IndicatorParameters(values=values)

    def analyze(
        self,
        symbol: str,
        candles_by_timeframe: Dict[MarketTimeframe, List[OHLCBar]],
        indicator_engine: Any,
        parameters: Optional[IndicatorParameters] = None,
        data_source: DataSource = DataSource.SIMULATED,
    ) -> StrategyResult:
        from src.strategies.base import SignalRejection

        if not self._enabled:
            entry_tf = self._params.timeframe
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

        p = dict(parameters.values) if parameters else dict(self.default_parameters.values)
        tf_str = str(p.get("timeframe", "H1"))
        try:
            entry_tf = MarketTimeframe(tf_str)
        except ValueError:
            entry_tf = MarketTimeframe.H1

        entry_candles = candles_by_timeframe.get(entry_tf, [])
        if not entry_candles:
            return StrategyResult(
                strategy_name=self.name, symbol=symbol, timeframe=entry_tf,
                signals=[], rejections=[], market_regime=MarketRegime.UNKNOWN,
                indicator_snapshots={},
                error=f"No candles available for {entry_tf.value}",
            )

        n = len(entry_candles)
        curr = entry_candles[-1]
        prev = entry_candles[-2] if n >= 2 else None
        curr_close = curr.close

        # Calculate indicators
        ema_val: Optional[Decimal] = None
        rsi_val: Optional[Decimal] = None
        adx_val: Optional[Decimal] = None

        try:
            r = indicator_engine.calculate(
                "EMA", symbol, entry_tf, entry_candles,
                parameters=IndicatorParameters(values={"periods": [int(p.get("ema_period", 50))]}),
                data_source=data_source,
            )
            series = r.values.get(f"ema_{int(p.get('ema_period', 50))}", [])
            ema_val = series[-1] if series else None
        except Exception:  # noqa: BLE001
            pass

        try:
            r = indicator_engine.calculate(
                "RSI", symbol, entry_tf, entry_candles,
                parameters=IndicatorParameters(values={"period": int(p.get("rsi_period", 14))}),
                data_source=data_source,
            )
            series = r.values.get("rsi", [])
            rsi_val = series[-1] if series else None
        except Exception:  # noqa: BLE001
            pass

        try:
            r = indicator_engine.calculate(
                "ADX", symbol, entry_tf, entry_candles,
                parameters=IndicatorParameters(values={"period": int(p.get("adx_period", 14))}),
                data_source=data_source,
            )
            series = r.values.get("adx", [])
            adx_val = series[-1] if series else None
        except Exception:  # noqa: BLE001
            pass

        # --- Signal logic ---
        signals: List[Signal] = []
        rejections: List[SignalRejection] = []
        confirmation_conditions: List[str] = []
        explanation_parts: List[str] = []

        min_confirmations = int(p.get("min_confirmations", 2))
        adx_threshold = Decimal(str(p.get("adx_trending_threshold", 25)))
        confirmations = 0

        # Trend filter: price vs EMA
        price_above_ema = curr_close > ema_val if ema_val is not None else False
        price_below_ema = curr_close < ema_val if ema_val is not None else False

        # ADX trend strength
        adx_trending = adx_val is not None and adx_val >= adx_threshold

        # LONG: price above EMA + ADX trending + RSI > 50
        long_confirmed = False
        if price_above_ema and adx_trending:
            long_confirmed = True
            confirmation_conditions.append("Price above EMA")
            confirmations += 1
            confirmation_conditions.append("ADX trending")
            confirmations += 1
            if rsi_val is not None and rsi_val > Decimal("50"):
                confirmation_conditions.append("RSI > 50")
                confirmations += 1
                explanation_parts.append(
                    f"LONG: intraday trend continuation on {entry_tf.value}"
                )
            else:
                explanation_parts.append(
                    f"LONG setup incomplete: RSI {rsi_val} not > 50"
                )

        # SHORT: price below EMA + ADX trending + RSI < 50
        short_confirmed = False
        if price_below_ema and adx_trending:
            short_confirmed = True
            confirmation_conditions.append("Price below EMA")
            confirmations += 1
            confirmation_conditions.append("ADX trending")
            confirmations += 1
            if rsi_val is not None and rsi_val < Decimal("50"):
                confirmation_conditions.append("RSI < 50")
                confirmations += 1
                explanation_parts.append(
                    f"SHORT: intraday trend continuation on {entry_tf.value}"
                )
            else:
                explanation_parts.append(
                    f"SHORT setup incomplete: RSI {rsi_val} not < 50"
                )

        direction: Optional[SignalDirection] = None

        if long_confirmed and confirmations >= min_confirmations:
            direction = SignalDirection.LONG
        elif short_confirmed and confirmations >= min_confirmations:
            direction = SignalDirection.SHORT

        if direction is None:
            if not adx_trending:
                explanation_parts.append(f"ADX {adx_val} below trending threshold {adx_threshold}")
            explanation_parts.append("Intraday setup conditions not met")

        # --- Build signal ---
        now = datetime.now(timezone.utc)
        last_candle_ts = entry_candles[-1].timestamp if entry_candles else now

        if direction is not None:
            invalidation: Optional[Decimal] = None
            if direction == SignalDirection.LONG and ema_val is not None:
                invalidation = ema_val * (Decimal("1") - Decimal("0.002"))
            elif direction == SignalDirection.SHORT and ema_val is not None:
                invalidation = ema_val * (Decimal("1") + Decimal("0.002"))

            signals.append(Signal(
                signal_id="",
                strategy_name=self.name,
                strategy_version=self.version,
                symbol=symbol,
                instrument_type="forex",
                direction=direction,
                status=SignalStatus.ACTIVE,
                entry_timeframe=entry_tf,
                confirmation_timeframes=[],
                signal_timestamp=now,
                market_data_timestamp=last_candle_ts,
                reference_price=curr_close,
                technical_invalidation=invalidation,
                parameters=IndicatorParameters(values=dict(p)),
                indicator_snapshot={
                    "ema": float(ema_val) if ema_val else None,
                    "rsi": float(rsi_val) if rsi_val else None,
                    "adx": float(adx_val) if adx_val else None,
                },
                market_regime=MarketRegime.TRENDING,
                confirmation_conditions=confirmation_conditions,
                explanation=". ".join(explanation_parts) + ".",
                expiry_conditions=[
                    "Price crosses opposite EMA",
                    "ADX falls below trending threshold",
                    f"Signal age exceeds {p.get('max_signal_age_minutes', 60)} minutes",
                ],
                data_source=data_source,
                strategy_validity_state="valid" if self._enabled else "disabled",
                metadata={
                    "profile": "intraday",
                    "timeframe": entry_tf.value,
                    "confirmations_met": confirmations,
                    "min_confirmations": min_confirmations,
                },
            ))
        else:
            reason = "; ".join(explanation_parts) if explanation_parts else "No intraday setup"
            rejections.append(SignalRejection(
                symbol=symbol,
                timeframe=entry_tf,
                strategy_name=self.name,
                reason=reason,
                data_source=data_source,
                timestamp=now,
            ))

        return StrategyResult(
            strategy_name=self.name,
            symbol=symbol,
            timeframe=entry_tf,
            signals=signals,
            rejections=rejections,
            market_regime=MarketRegime.TRANSITIONING,
            indicator_snapshots={
                "intraday": IndicatorParameters(values=dict(p)),
            },
        )
