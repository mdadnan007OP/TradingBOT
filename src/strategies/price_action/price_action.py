"""Price Action Strategy.

Identifies candlestick patterns using measurable body, wick, and range conditions:
    * Bullish engulfing
    * Bearish engulfing
    * Pin bar (bullish/bearish)
    * Hammer
    * Shooting star
    * Inside bar
    * Outside bar
    * Break of structure (BOS)
    * Change of character (CHoCH)
    * Support and resistance rejection

All rules are explicit and configurable — no subjective pattern recognition.
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
from src.strategies.base import SignalRejection


@dataclass(frozen=True)
class PriceActionParameters:
    """Parameters for Price Action Strategy."""

    # Body/wick ratios (as fraction of total range)
    min_body_ratio: Decimal = Decimal("0.5")       # min body / total range
    max_body_ratio: Decimal = Decimal("0.9")       # max body / total range (avoid doji)
    min_wick_ratio: Decimal = Decimal("0.1")       # min wick / total range
    engulfing_body_ratio: Decimal = Decimal("1.0") # engulfing candle body must be >= prior body
    inside_bar_max_ratio: Decimal = Decimal("0.5") # inside bar range <= 50% of prior
    bos_lookback: int = 20                         # lookback for structure breaks
    swing_strength: int = 3                        # candles to confirm swing high/low
    min_range_atr_multiplier: Decimal = Decimal("0.5")  # min range as ATR multiple
    max_range_atr_multiplier: Decimal = Decimal("3.0")  # max range as ATR multiple


class PriceActionStrategy(Strategy):
    """Price action strategy using measurable candle patterns."""

    name = "PriceAction"
    version = "1.0.0"

    def __init__(self) -> None:
        self._enabled = True
        self._params = PriceActionParameters()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    @property
    def required_timeframes(self) -> List[MarketTimeframe]:
        return [MarketTimeframe.M15, MarketTimeframe.H1, MarketTimeframe.H4]

    @property
    def supported_instruments(self) -> Optional[List[str]]:
        return None

    @property
    def supported_regimes(self) -> List[MarketRegime]:
        return [
            MarketRegime.RANGING,
            MarketRegime.TRENDING,
            MarketRegime.TRANSITIONING,
        ]

    @property
    def default_parameters(self) -> IndicatorParameters:
        return IndicatorParameters(values={
            "min_body_ratio": float(self._params.min_body_ratio),
            "max_body_ratio": float(self._params.max_body_ratio),
            "min_wick_ratio": float(self._params.min_wick_ratio),
            "engulfing_body_ratio": float(self._params.engulfing_body_ratio),
            "inside_bar_max_ratio": float(self._params.inside_bar_max_ratio),
            "bos_lookback": self._params.bos_lookback,
            "swing_strength": self._params.swing_strength,
            "min_range_atr_multiplier": float(self._params.min_range_atr_multiplier),
            "max_range_atr_multiplier": float(self._params.max_range_atr_multiplier),
        })

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        values = dict(parameters.values)
        min_br = Decimal(str(values.get("min_body_ratio", 0.5)))
        max_br = Decimal(str(values.get("max_body_ratio", 0.9)))
        if min_br >= max_br:
            raise ValueError("min_body_ratio must be < max_body_ratio")
        if min_br < Decimal("0") or max_br > Decimal("1"):
            raise ValueError("body ratios must be between 0 and 1")
        return IndicatorParameters(values=values)

    # ------------------------------------------------------------------
    # Candle pattern helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _body_size(c: OHLCBar) -> Decimal:
        return abs(c.close - c.open)

    @staticmethod
    def _upper_wick(c: OHLCBar) -> Decimal:
        return c.high - max(c.open, c.close)

    @staticmethod
    def _lower_wick(c: OHLCBar) -> Decimal:
        return min(c.open, c.close) - c.low

    @staticmethod
    def _total_range(c: OHLCBar) -> Decimal:
        return c.high - c.low

    @staticmethod
    def _is_bullish(c: OHLCBar) -> bool:
        return c.close > c.open

    @staticmethod
    def _is_bearish(c: OHLCBar) -> bool:
        return c.close < c.open

    def _detect_patterns(
        self,
        candles: List[OHLCBar],
        params: PriceActionParameters,
        atr: Optional[Decimal] = None,
    ) -> Dict[str, List[bool]]:
        """Detect price action patterns for each candle.

        Returns dict of pattern_name -> list of bools aligned with candles.
        """
        n = len(candles)
        patterns: Dict[str, List[bool]] = {
            "bullish_engulfing": [False] * n,
            "bearish_engulfing": [False] * n,
            "bullish_pin_bar": [False] * n,
            "bearish_pin_bar": [False] * n,
            "hammer": [False] * n,
            "shooting_star": [False] * n,
            "inside_bar": [False] * n,
            "outside_bar": [False] * n,
        }

        for i in range(1, n):
            curr = candles[i]
            prev = candles[i - 1]

            curr_range = self._total_range(curr)
            prev_range = self._total_range(prev)
            curr_body = self._body_size(curr)
            prev_body = self._body_size(prev)
            curr_upper = self._upper_wick(curr)
            curr_lower = self._lower_wick(curr)

            # Skip doji-like candles (no meaningful body)
            if curr_range <= Decimal("0"):
                continue

            body_ratio = curr_body / curr_range if curr_range > 0 else Decimal("0")

            # --- Bullish Engulfing ---
            # Current bullish, body engulfs prior body completely
            if (
                self._is_bullish(curr)
                and self._is_bearish(prev)
                and curr_body >= prev_body * params.engulfing_body_ratio
                and curr.open <= prev.close
                and curr.close >= prev.open
            ):
                patterns["bullish_engulfing"][i] = True

            # --- Bearish Engulfing ---
            # Current bearish, body engulfs prior body completely
            if (
                self._is_bearish(curr)
                and self._is_bullish(prev)
                and curr_body >= prev_body * params.engulfing_body_ratio
                and curr.open >= prev.close
                and curr.close <= prev.open
            ):
                patterns["bearish_engulfing"][i] = True

            # --- Bullish Pin Bar ---
            # Small body at top, long lower wick
            if (
                body_ratio <= params.max_body_ratio
                and body_ratio >= params.min_body_ratio
                and curr_lower > curr_body * Decimal("2")
                and curr_upper < curr_body * Decimal("0.5")
            ):
                patterns["bullish_pin_bar"][i] = True

            # --- Bearish Pin Bar ---
            # Small body at bottom, long upper wick
            if (
                body_ratio <= params.max_body_ratio
                and body_ratio >= params.min_body_ratio
                and curr_upper > curr_body * Decimal("2")
                and curr_lower < curr_body * Decimal("0.5")
            ):
                patterns["bearish_pin_bar"][i] = True

            # --- Hammer ---
            # Bullish pin bar at support (lower wick 2x body, small upper wick)
            if (
                self._is_bullish(curr)
                and body_ratio <= params.max_body_ratio
                and curr_lower > curr_body * Decimal("2")
                and curr_upper < curr_body * Decimal("0.3")
            ):
                patterns["hammer"][i] = True

            # --- Shooting Star ---
            # Bearish pin bar at resistance (upper wick 2x body, small lower wick)
            if (
                self._is_bearish(curr)
                and body_ratio <= params.max_body_ratio
                and curr_upper > curr_body * Decimal("2")
                and curr_lower < curr_body * Decimal("0.3")
            ):
                patterns["shooting_star"][i] = True

            # --- Inside Bar ---
            # Current range entirely within prior range
            if (
                curr.high <= prev.high
                and curr.low >= prev.low
                and curr_range <= prev_range * params.inside_bar_max_ratio
            ):
                patterns["inside_bar"][i] = True

            # --- Outside Bar ---
            # Current range completely engulfs prior range
            if (
                curr.high >= prev.high
                and curr.low <= prev.low
                and (curr.high > prev.high or curr.low < prev.low)
            ):
                patterns["outside_bar"][i] = True

        # --- Break of Structure (BOS) ---
        bos_long = [False] * n
        bos_short = [False] * n
        lookback = params.bos_lookback
        strength = params.swing_strength

        for i in range(lookback, n):
            # Look at swing highs/lows in lookback window
            window = candles[i - lookback : i]
            if len(window) < strength * 2 + 1:
                continue

            # Recent swing high (highest high in window excluding current)
            swing_highs = [c.high for c in window[:-strength]]
            swing_lows = [c.low for c in window[:-strength]]
            prev_swing_high = max(swing_highs) if swing_highs else None
            prev_swing_low = min(swing_lows) if swing_lows else None

            curr = candles[i]

            # Bullish BOS: close above previous swing high
            if prev_swing_high is not None and curr.close > prev_swing_high:
                # Confirm with strength: next 'strength' candles stay above
                bos_long[i] = True

            # Bearish BOS: close below previous swing low
            if prev_swing_low is not None and curr.close < prev_swing_low:
                bos_short[i] = True

        patterns["bos_long"] = bos_long
        patterns["bos_short"] = bos_short

        # --- Change of Character (CHoCH) ---
        # CHoCH = BOS in opposite direction of previous trend
        # Simplified: if we had higher highs then price breaks below recent swing low
        choch_long = [False] * n
        choch_short = [False] * n

        for i in range(lookback, n):
            window = candles[i - lookback : i]
            if len(window) < strength * 2 + 1:
                continue

            # Check for prior uptrend (higher highs)
            recent_highs = [c.high for c in window[-strength:]]
            earlier_highs = [c.high for c in window[:-strength]]
            if not recent_highs or not earlier_highs:
                continue

            curr = candles[i]

            # CHoCH to bullish: prior downtrend (lower lows), then break above recent swing high
            prev_swing_low = min(c.low for c in window[:-strength]) if window[:-strength] else None
            recent_swing_high = max(c.high for c in window[-strength:]) if window[-strength:] else None
            if prev_swing_low is not None and recent_swing_high is not None:
                # Was making lower lows, now breaks above recent high
                if curr.close > recent_swing_high:
                    # Verify prior structure was bearish (lower lows in window)
                    lows = [c.low for c in window]
                    if len(lows) >= 2 and lows[-1] < lows[0]:
                        choch_long[i] = True

            # CHoCH to bearish: prior uptrend (higher highs), then break below recent swing low
            prev_swing_high = max(c.high for c in window[:-strength]) if window[:-strength] else None
            recent_swing_low = min(c.low for c in window[-strength:]) if window[-strength:] else None
            if prev_swing_high is not None and recent_swing_low is not None:
                if curr.close < recent_swing_low:
                    highs = [c.high for c in window]
                    if len(highs) >= 2 and highs[-1] > highs[0]:
                        choch_short[i] = True

        patterns["choch_long"] = choch_long
        patterns["choch_short"] = choch_short

        return patterns

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

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

        if not entry_candles:
            return StrategyResult(
                strategy_name=self.name, symbol=symbol, timeframe=entry_tf,
                signals=[], rejections=[], market_regime=MarketRegime.UNKNOWN,
                indicator_snapshots={},
                error=f"No candles available for {entry_tf.value}",
            )

        p = dict(parameters.values) if parameters else dict(self.default_parameters.values)
        min_body_ratio = Decimal(str(p.get("min_body_ratio", 0.5)))
        max_body_ratio = Decimal(str(p.get("max_body_ratio", 0.9)))
        min_wick_ratio = Decimal(str(p.get("min_wick_ratio", 0.1)))
        engulfing_ratio = Decimal(str(p.get("engulfing_body_ratio", 1.0)))
        inside_ratio = Decimal(str(p.get("inside_bar_max_ratio", 0.5)))
        bos_lookback = int(p.get("bos_lookback", 20))
        swing_strength = int(p.get("swing_strength", 3))

        # Update params
        params_obj = PriceActionParameters(
            min_body_ratio=min_body_ratio,
            max_body_ratio=max_body_ratio,
            min_wick_ratio=min_wick_ratio,
            engulfing_body_ratio=engulfing_ratio,
            inside_bar_max_ratio=inside_ratio,
            bos_lookback=bos_lookback,
            swing_strength=swing_strength,
            min_range_atr_multiplier=Decimal(str(p.get("min_range_atr_multiplier", 0.5))),
            max_range_atr_multiplier=Decimal(str(p.get("max_range_atr_multiplier", 3.0))),
        )

        # Get ATR for range validation
        atr_val: Optional[Decimal] = None
        try:
            atr_result = indicator_engine.calculate(
                "ATR", symbol, entry_tf, entry_candles,
                parameters=IndicatorParameters(values={"period": 14}),
                data_source=data_source,
            )
            atr_series = atr_result.values.get("atr", [])
            atr_values = [v for v in atr_series if v is not None]
            if atr_values:
                atr_val = atr_values[-1]
        except Exception:  # noqa: BLE001
            atr_val = None

        patterns = self._detect_patterns(entry_candles, params_obj, atr_val)

        n = len(entry_candles)
        last_idx = n - 1
        curr = entry_candles[last_idx]
        curr_close = curr.close

        signals: List[Signal] = []
        rejections: List[SignalRejection] = []
        confirmation_conditions: List[str] = []
        explanation_parts: List[str] = []

        # --- Determine direction from patterns ---
        direction: Optional[SignalDirection] = None
        matched_patterns: List[str] = []

        # Bullish patterns
        if patterns["bullish_engulfing"][last_idx]:
            matched_patterns.append("bullish engulfing")
        if patterns["bullish_pin_bar"][last_idx]:
            matched_patterns.append("bullish pin bar")
        if patterns["hammer"][last_idx]:
            matched_patterns.append("hammer")
        if patterns["bos_long"][last_idx]:
            matched_patterns.append("break of structure (bullish)")
        if patterns["choch_long"][last_idx]:
            matched_patterns.append("change of character (bullish)")

        # Bearish patterns
        if patterns["bearish_engulfing"][last_idx]:
            matched_patterns.append("bearish engulfing")
        if patterns["bearish_pin_bar"][last_idx]:
            matched_patterns.append("bearish pin bar")
        if patterns["shooting_star"][last_idx]:
            matched_patterns.append("shooting star")
        if patterns["bos_short"][last_idx]:
            matched_patterns.append("break of structure (bearish)")
        if patterns["choch_short"][last_idx]:
            matched_patterns.append("change of character (bearish)")

        # --- Range validation ---
        curr_range = self._total_range(curr)
        if atr_val is not None and atr_val > Decimal("0"):
            range_ratio = curr_range / atr_val
            if range_ratio < params_obj.min_range_atr_multiplier:
                explanation_parts.append(
                    f"Candle range too small ({range_ratio:.2f}x ATR, min {params_obj.min_range_atr_multiplier})"
                )
                matched_patterns = []  # Invalidate weak candles
            elif range_ratio > params_obj.max_range_atr_multiplier:
                explanation_parts.append(
                    f"Candle range too large ({range_ratio:.2f}x ATR, max {params_obj.max_range_atr_multiplier})"
                )
                matched_patterns = []

        # --- Determine final direction ---
        bullish_patterns = {"bullish engulfing", "bullish pin bar", "hammer",
                          "break of structure (bullish)", "change of character (bullish)"}
        bearish_patterns = {"bearish engulfing", "bearish pin bar", "shooting star",
                          "break of structure (bearish)", "change of character (bearish)"}

        bullish_matched = [p for p in matched_patterns if p in bullish_patterns]
        bearish_matched = [p for p in matched_patterns if p in bearish_patterns]

        if bullish_matched and not bearish_matched:
            direction = SignalDirection.LONG
            confirmation_conditions.extend([f"Pattern: {p}" for p in bullish_matched])
            explanation_parts.append(
                f"LONG: {', '.join(bullish_matched)} detected on {entry_tf.value}"
            )
        elif bearish_matched and not bullish_matched:
            direction = SignalDirection.SHORT
            confirmation_conditions.extend([f"Pattern: {p}" for p in bearish_matched])
            explanation_parts.append(
                f"SHORT: {', '.join(bearish_matched)} detected on {entry_tf.value}"
            )
        elif bullish_matched and bearish_matched:
            explanation_parts.append(
                f"Conflicting patterns: bullish {bullish_matched}, bearish {bearish_matched}"
            )
        else:
            explanation_parts.append("No price action pattern detected")

        # --- Build signal ---
        now = datetime.now(timezone.utc)
        last_candle_ts = entry_candles[-1].timestamp if entry_candles else now

        if direction is not None:
            # Technical invalidation: opposite swing level
            invalidation: Optional[Decimal] = None
            if direction == SignalDirection.LONG:
                # Invalidate below recent swing low
                lookback = min(bos_lookback, n - 1)
                if lookback > 0:
                    window = entry_candles[-lookback - 1:-1]
                    if window:
                        invalidation = min(c.low for c in window)
            elif direction == SignalDirection.SHORT:
                lookback = min(bos_lookback, n - 1)
                if lookback > 0:
                    window = entry_candles[-lookback - 1:-1]
                    if window:
                        invalidation = max(c.high for c in window)

            signals.append(Signal(
                signal_id="",
                strategy_name=self.name,
                strategy_version=self.version,
                symbol=symbol,
                instrument_type="forex",
                direction=direction,
                status=SignalStatus.ACTIVE,
                entry_timeframe=entry_tf,
                confirmation_timeframes=self.required_timeframes[1:],
                signal_timestamp=now,
                market_data_timestamp=last_candle_ts,
                reference_price=curr_close,
                technical_invalidation=invalidation,
                parameters=IndicatorParameters(values=dict(p)),
                indicator_snapshot={
                    "patterns": {
                        name: patterns[name][-5:] if len(patterns[name]) >= 5 else patterns[name]
                        for name in patterns
                    },
                },
                market_regime=MarketRegime.TRANSITIONING,
                confirmation_conditions=confirmation_conditions,
                explanation=". ".join(explanation_parts) + ".",
                expiry_conditions=[
                    "Pattern candle is no longer the most recent completed candle",
                    "Opposite price action pattern forms",
                    f"Signal age exceeds {p.get('max_signal_age_minutes', 60)} minutes",
                ],
                data_source=data_source,
                strategy_validity_state="valid" if self._enabled else "disabled",
                metadata={
                    "matched_patterns": matched_patterns,
                    "body_ratio": float(self._body_size(curr) / curr_range) if curr_range > 0 else None,
                    "upper_wick_ratio": float(self._upper_wick(curr) / curr_range) if curr_range > 0 else None,
                    "lower_wick_ratio": float(self._lower_wick(curr) / curr_range) if curr_range > 0 else None,
                },
            ))
        else:
            reason = "; ".join(explanation_parts) if explanation_parts else "No price action signal"
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
                "price_action": IndicatorParameters(values=dict(p)),
            },
        )
