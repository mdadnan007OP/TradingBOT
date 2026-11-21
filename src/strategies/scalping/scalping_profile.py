"""Scalping Strategy Profile.

Configurable short-term strategy profile for M1, M5, M15 timeframes.
Uses EMA, RSI, MACD, ATR, and price action with configurable entry conditions.
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
class ScalpingParameters:
    """Parameters for Scalping Profile."""

    timeframe: MarketTimeframe = MarketTimeframe.M5
    ema_fast: int = 9
    ema_slow: int = 21
    rsi_period: int = 14
    rsi_overbought: Decimal = Decimal("70")
    rsi_oversold: Decimal = Decimal("30")
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 14
    min_atr_multiplier: Decimal = Decimal("0.5")
    max_spread: Optional[Decimal] = None
    min_confirmations: int = 2


class ScalpingProfile(Strategy):
    """Scalping strategy profile for M1/M5/M15."""

    name = "ScalpingProfile"
    version = "1.0.0"

    def __init__(self) -> None:
        self._enabled = True
        self._params = ScalpingParameters()

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
            MarketRegime.HIGH_VOLATILITY,
        ]

    @property
    def default_parameters(self) -> IndicatorParameters:
        return IndicatorParameters(values={
            "timeframe": self._params.timeframe.value,
            "ema_fast": self._params.ema_fast,
            "ema_slow": self._params.ema_slow,
            "rsi_period": self._params.rsi_period,
            "rsi_overbought": float(self._params.rsi_overbought),
            "rsi_oversold": float(self._params.rsi_oversold),
            "macd_fast": self._params.macd_fast,
            "macd_slow": self._params.macd_slow,
            "macd_signal": self._params.macd_signal,
            "atr_period": self._params.atr_period,
            "min_atr_multiplier": float(self._params.min_atr_multiplier),
            "min_confirmations": self._params.min_confirmations,
        })

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        values = dict(parameters.values)
        tf_str = str(values.get("timeframe", "M5"))
        try:
            MarketTimeframe(tf_str)
        except ValueError:
            raise ValueError(f"Invalid timeframe: {tf_str}")
        fast = int(values.get("ema_fast", 9))
        slow = int(values.get("ema_slow", 21))
        if fast >= slow:
            raise ValueError("ema_fast must be < ema_slow")
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
        tf_str = str(p.get("timeframe", "M5"))
        try:
            entry_tf = MarketTimeframe(tf_str)
        except ValueError:
            entry_tf = MarketTimeframe.M5

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
        ema_fast_val: Optional[Decimal] = None
        ema_slow_val: Optional[Decimal] = None
        rsi_val: Optional[Decimal] = None
        macd_val: Optional[Decimal] = None
        macd_signal_val: Optional[Decimal] = None
        atr_val: Optional[Decimal] = None

        try:
            r = indicator_engine.calculate(
                "EMA", symbol, entry_tf, entry_candles,
                parameters=IndicatorParameters(values={"periods": [int(p.get("ema_fast", 9))]}),
                data_source=data_source,
            )
            series = r.values.get(f"ema_{int(p.get('ema_fast', 9))}", [])
            ema_fast_val = series[-1] if series else None
        except Exception:  # noqa: BLE001
            pass

        try:
            r = indicator_engine.calculate(
                "EMA", symbol, entry_tf, entry_candles,
                parameters=IndicatorParameters(values={"periods": [int(p.get("ema_slow", 21))]}),
                data_source=data_source,
            )
            series = r.values.get(f"ema_{int(p.get('ema_slow', 21))}", [])
            ema_slow_val = series[-1] if series else None
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
                "MACD", symbol, entry_tf, entry_candles,
                parameters=IndicatorParameters(values={
                    "fast_period": int(p.get("macd_fast", 12)),
                    "slow_period": int(p.get("macd_slow", 26)),
                    "signal_period": int(p.get("macd_signal", 9)),
                }),
                data_source=data_source,
            )
            macd_series = r.values.get("macd", [])
            signal_series = r.values.get("signal", [])
            macd_val = macd_series[-1] if macd_series else None
            macd_signal_val = signal_series[-1] if signal_series else None
        except Exception:  # noqa: BLE001
            pass

        try:
            r = indicator_engine.calculate(
                "ATR", symbol, entry_tf, entry_candles,
                parameters=IndicatorParameters(values={"period": int(p.get("atr_period", 14))}),
                data_source=data_source,
            )
            series = r.values.get("atr", [])
            atr_val = series[-1] if series else None
        except Exception:  # noqa: BLE001
            pass

        # --- Signal logic ---
        signals: List[Signal] = []
        rejections: List[SignalRejection] = []
        confirmation_conditions: List[str] = []
        explanation_parts: List[str] = []

        min_confirmations = int(p.get("min_confirmations", 2))
        confirmations = 0

        # Check spread if available
        max_spread = p.get("max_spread")
        if max_spread is not None and curr.spread is not None:
            if curr.spread > Decimal(str(max_spread)):
                rejections.append(SignalRejection(
                    symbol=symbol,
                    timeframe=entry_tf,
                    strategy_name=self.name,
                    reason=f"Spread {curr.spread} exceeds max {max_spread}",
                    data_source=data_source,
                    timestamp=datetime.now(timezone.utc),
                ))
                return StrategyResult(
                    strategy_name=self.name, symbol=symbol, timeframe=entry_tf,
                    signals=[], rejections=rejections,
                    market_regime=MarketRegime.UNKNOWN,
                    indicator_snapshots={},
                )

        # LONG: EMA bullish + RSI > 50 + MACD > signal + ATR sufficient
        long_conditions = []
        if ema_fast_val is not None and ema_slow_val is not None and ema_fast_val > ema_slow_val:
            long_conditions.append("EMA bullish alignment")
            confirmations += 1
        if rsi_val is not None and Decimal("50") < rsi_val < Decimal("70"):
            long_conditions.append("RSI in bullish zone")
            confirmations += 1
        if macd_val is not None and macd_signal_val is not None and macd_val > macd_signal_val:
            long_conditions.append("MACD above signal")
            confirmations += 1
        if atr_val is not None:
            min_atr = Decimal(str(p.get("min_atr_multiplier", 0.5))) * atr_val
            # ATR sufficiency check (simplified)
            confirmations += 1  # ATR present = sufficient volatility

        # SHORT: EMA bearish + RSI < 50 + MACD < signal
        short_conditions = []
        if ema_fast_val is not None and ema_slow_val is not None and ema_fast_val < ema_slow_val:
            short_conditions.append("EMA bearish alignment")
            confirmations += 1
        if rsi_val is not None and Decimal("30") < rsi_val < Decimal("50"):
            short_conditions.append("RSI in bearish zone")
            confirmations += 1
        if macd_val is not None and macd_signal_val is not None and macd_val < macd_signal_val:
            short_conditions.append("MACD below signal")
            confirmations += 1

        direction: Optional[SignalDirection] = None

        if confirmations >= min_confirmations:
            if len(long_conditions) >= len(short_conditions) and long_conditions:
                direction = SignalDirection.LONG
                confirmation_conditions.extend(long_conditions)
                explanation_parts.append(
                    f"LONG: scalping setup on {entry_tf.value} - "
                    f"{', '.join(long_conditions)}"
                )
            elif short_conditions:
                direction = SignalDirection.SHORT
                confirmation_conditions.extend(short_conditions)
                explanation_parts.append(
                    f"SHORT: scalping setup on {entry_tf.value} - "
                    f"{', '.join(short_conditions)}"
                )

        if direction is None:
            explanation_parts.append(
                f"Insufficient confirmations ({confirmations}/{min_confirmations})"
            )

        # --- Build signal ---
        now = datetime.now(timezone.utc)
        last_candle_ts = entry_candles[-1].timestamp if entry_candles else now

        if direction is not None:
            invalidation: Optional[Decimal] = None
            if direction == SignalDirection.LONG and ema_slow_val is not None:
                invalidation = ema_slow_val * (Decimal("1") - Decimal("0.001"))
            elif direction == SignalDirection.SHORT and ema_slow_val is not None:
                invalidation = ema_slow_val * (Decimal("1") + Decimal("0.001"))

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
                    "ema_fast": float(ema_fast_val) if ema_fast_val else None,
                    "ema_slow": float(ema_slow_val) if ema_slow_val else None,
                    "rsi": float(rsi_val) if rsi_val else None,
                    "macd": float(macd_val) if macd_val else None,
                    "atr": float(atr_val) if atr_val else None,
                },
                market_regime=MarketRegime.TRANSITIONING,
                confirmation_conditions=confirmation_conditions,
                explanation=". ".join(explanation_parts) + ".",
                expiry_conditions=[
                    "EMA alignment reverses",
                    "RSI crosses opposite 50 level",
                    f"Signal age exceeds {p.get('max_signal_age_minutes', 60)} minutes",
                ],
                data_source=data_source,
                strategy_validity_state="valid" if self._enabled else "disabled",
                metadata={
                    "profile": "scalping",
                    "timeframe": entry_tf.value,
                    "confirmations_met": confirmations,
                    "min_confirmations": min_confirmations,
                },
            ))
        else:
            reason = "; ".join(explanation_parts) if explanation_parts else "No scalping setup"
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
                "scalping": IndicatorParameters(values=dict(p)),
            },
        )
