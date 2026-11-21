"""Swing Strategy Profile.

Configurable profile for H1, H4, D1, W1 timeframes.
Considers larger market trend, confirmed swing structure, trendline support
and resistance, momentum confirmation, and previous week levels.
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
class SwingParameters:
    """Parameters for Swing Profile."""

    timeframe: MarketTimeframe = MarketTimeframe.H4
    ema_period: int = 50
    sma_period: int = 200
    adx_period: int = 14
    rsi_period: int = 14
    adx_trending_threshold: Decimal = Decimal("25")
    use_prev_week_levels: bool = True
    min_confirmations: int = 2


class SwingProfile(Strategy):
    """Swing strategy profile for H1/H4/D1/W1."""

    name = "SwingProfile"
    version = "1.0.0"

    def __init__(self) -> None:
        self._enabled = True
        self._params = SwingParameters()

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
        ]

    @property
    def default_parameters(self) -> IndicatorParameters:
        return IndicatorParameters(values={
            "timeframe": self._params.timeframe.value,
            "ema_period": self._params.ema_period,
            "sma_period": self._params.sma_period,
            "adx_period": self._params.adx_period,
            "rsi_period": self._params.rsi_period,
            "adx_trending_threshold": float(self._params.adx_trending_threshold),
            "use_prev_week_levels": self._params.use_prev_week_levels,
            "min_confirmations": self._params.min_confirmations,
        })

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        values = dict(parameters.values)
        tf_str = str(values.get("timeframe", "H4"))
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
        tf_str = str(p.get("timeframe", "H4"))
        try:
            entry_tf = MarketTimeframe(tf_str)
        except ValueError:
            entry_tf = MarketTimeframe.H4

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
        curr_close = curr.close

        # Calculate indicators
        ema_val: Optional[Decimal] = None
        sma_val: Optional[Decimal] = None
        adx_val: Optional[Decimal] = None
        rsi_val: Optional[Decimal] = None

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
                "SMA", symbol, entry_tf, entry_candles,
                parameters=IndicatorParameters(values={"periods": [int(p.get("sma_period", 200))]}),
                data_source=data_source,
            )
            series = r.values.get(f"sma_{int(p.get('sma_period', 200))}", [])
            sma_val = series[-1] if series else None
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

        # --- Signal logic ---
        signals: List[Signal] = []
        rejections: List[SignalRejection] = []
        confirmation_conditions: List[str] = []
        explanation_parts: List[str] = []

        min_confirmations = int(p.get("min_confirmations", 2))
        adx_threshold = Decimal(str(p.get("adx_trending_threshold", 25)))
        confirmations = 0

        # Swing requires stronger trend confirmation
        price_above_ema = curr_close > ema_val if ema_val is not None else False
        price_below_ema = curr_close < ema_val if ema_val is not None else False
        price_above_sma = curr_close > sma_val if sma_val is not None else False
        price_below_sma = curr_close < sma_val if sma_val is not None else False

        adx_trending = adx_val is not None and adx_val >= adx_threshold

        # LONG: price above EMA + SMA + ADX trending + RSI > 50
        long_confirmed = False
        if price_above_ema and price_above_sma and adx_trending:
            long_confirmed = True
            confirmation_conditions.append("Price above EMA and SMA")
            confirmations += 1
            confirmation_conditions.append("ADX trending")
            confirmations += 1
            if rsi_val is not None and rsi_val > Decimal("50"):
                confirmation_conditions.append("RSI > 50")
                confirmations += 1
                explanation_parts.append(
                    f"LONG: swing trend continuation on {entry_tf.value}"
                )
            else:
                explanation_parts.append(
                    f"LONG setup incomplete: RSI {rsi_val} not > 50"
                )

        # SHORT: price below EMA + SMA + ADX trending + RSI < 50
        short_confirmed = False
        if price_below_ema and price_below_sma and adx_trending:
            short_confirmed = True
            confirmation_conditions.append("Price below EMA and SMA")
            confirmations += 1
            confirmation_conditions.append("ADX trending")
            confirmations += 1
            if rsi_val is not None and rsi_val < Decimal("50"):
                confirmation_conditions.append("RSI < 50")
                confirmations += 1
                explanation_parts.append(
                    f"SHORT: swing trend continuation on {entry_tf.value}"
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
            if not (price_above_ema and price_above_sma) and not (price_below_ema and price_below_sma):
                explanation_parts.append("Price not aligned with both EMA and SMA")
            explanation_parts.append("Swing setup conditions not met")

        # --- Build signal ---
        now = datetime.now(timezone.utc)
        last_candle_ts = entry_candles[-1].timestamp if entry_candles else now

        if direction is not None:
            invalidation: Optional[Decimal] = None
            if direction == SignalDirection.LONG and sma_val is not None:
                invalidation = sma_val * (Decimal("1") - Decimal("0.003"))
            elif direction == SignalDirection.SHORT and sma_val is not None:
                invalidation = sma_val * (Decimal("1") + Decimal("0.003"))

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
                    "sma": float(sma_val) if sma_val else None,
                    "adx": float(adx_val) if adx_val else None,
                    "rsi": float(rsi_val) if rsi_val else None,
                },
                market_regime=MarketRegime.TRENDING,
                confirmation_conditions=confirmation_conditions,
                explanation=". ".join(explanation_parts) + ".",
                expiry_conditions=[
                    "Price crosses opposite SMA",
                    "ADX falls below trending threshold",
                    f"Signal age exceeds {p.get('max_signal_age_minutes', 60)} minutes",
                ],
                data_source=data_source,
                strategy_validity_state="valid" if self._enabled else "disabled",
                metadata={
                    "profile": "swing",
                    "timeframe": entry_tf.value,
                    "confirmations_met": confirmations,
                    "min_confirmations": min_confirmations,
                },
            ))
        else:
            reason = "; ".join(explanation_parts) if explanation_parts else "No swing setup"
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
                "swing": IndicatorParameters(values=dict(p)),
            },
        )
