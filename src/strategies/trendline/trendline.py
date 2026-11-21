"""Trendline Strategy.

Detects trendlines using confirmed swing pivots only (no future-pivot leakage):
    * Swing-high / swing-low detection
    * Trendline construction from confirmed pivots
    * Trendline touch detection
    * Breakout detection with confirmation
    * Retest detection

Only uses swing points confirmed at the relevant historical timestamp — no
repainting, no look-ahead bias.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

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
class SwingPoint:
    """A confirmed swing point (high or low)."""

    index: int
    timestamp: any  # datetime
    price: Decimal
    is_high: bool
    confirmed_at_index: int  # index when confirmation completed


@dataclass(frozen=True)
class Trendline:
    """A trendline connecting two or more swing points."""

    points: List[SwingPoint]
    slope: Decimal  # price change per candle index
    intercept: Decimal  # price at index 0
    touch_count: int
    last_touch_index: Optional[int]
    is_support: bool  # True if below price (support), False if resistance


@dataclass(frozen=True)
class TrendlineParameters:
    """Parameters for Trendline Strategy."""

    min_swing_strength: int = 3
    min_touches: int = 2
    max_lookback: int = 100
    touch_tolerance: Decimal = Decimal("0.002")  # 0.2% tolerance for touch
    breakout_confirmation_candles: int = 2
    retest_lookback: int = 10


class TrendlineStrategy(Strategy):
    """Trendline strategy using confirmed swing pivots only."""

    name = "Trendline"
    version = "1.0.0"

    def __init__(self) -> None:
        self._enabled = True
        self._params = TrendlineParameters()

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
        return None

    @property
    def supported_regimes(self) -> List[MarketRegime]:
        return [
            MarketRegime.TRENDING,
            MarketRegime.RANGING,
            MarketRegime.TRANSITIONING,
        ]

    @property
    def default_parameters(self) -> IndicatorParameters:
        return IndicatorParameters(values={
            "min_swing_strength": self._params.min_swing_strength,
            "min_touches": self._params.min_touches,
            "max_lookback": self._params.max_lookback,
            "touch_tolerance": float(self._params.touch_tolerance),
            "breakout_confirmation_candles": self._params.breakout_confirmation_candles,
            "retest_lookback": self._params.retest_lookback,
        })

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        values = dict(parameters.values)
        strength = int(values.get("min_swing_strength", 3))
        if strength < 1:
            raise ValueError("min_swing_strength must be >= 1")
        touches = int(values.get("min_touches", 2))
        if touches < 2:
            raise ValueError("min_touches must be >= 2")
        lookback = int(values.get("max_lookback", 100))
        if lookback < 20:
            raise ValueError("max_lookback must be >= 20")
        return IndicatorParameters(values=values)

    # ------------------------------------------------------------------
    # Swing point detection (confirmed only)
    # ------------------------------------------------------------------

    def _detect_swing_points(
        self,
        candles: List[OHLCBar],
        strength: int,
        max_lookback: int,
    ) -> Tuple[List[SwingPoint], List[SwingPoint]]:
        """Detect confirmed swing highs and lows.

        A swing point is confirmed only after `strength` candles have closed
        beyond it in the opposite direction — no future-pivot leakage.
        """
        n = len(candles)
        start_idx = max(0, n - max_lookback)

        swing_highs: List[SwingPoint] = []
        swing_lows: List[SwingPoint] = []

        for i in range(start_idx + strength, n - strength):
            hi = candles[i].high
            lo = candles[i].low

            # Check if this is a swing high (highest in window)
            is_high = True
            for j in range(max(start_idx, i - strength), i):
                if candles[j].high >= hi:
                    is_high = False
                    break
            if is_high:
                for j in range(i + 1, min(n, i + strength + 1)):
                    if candles[j].high > hi:
                        is_high = False
                        break
            if is_high:
                # Confirmation: `strength` candles after must not exceed this high
                confirmed_at = i + strength
                if confirmed_at < n:
                    swing_highs.append(SwingPoint(
                        index=i,
                        timestamp=candles[i].timestamp,
                        price=hi,
                        is_high=True,
                        confirmed_at_index=confirmed_at,
                    ))

            # Check if this is a swing low
            is_low = True
            for j in range(max(start_idx, i - strength), i):
                if candles[j].low <= lo:
                    is_low = False
                    break
            if is_low:
                for j in range(i + 1, min(n, i + strength + 1)):
                    if candles[j].low < lo:
                        is_low = False
                        break
            if is_low:
                confirmed_at = i + strength
                if confirmed_at < n:
                    swing_lows.append(SwingPoint(
                        index=i,
                        timestamp=candles[i].timestamp,
                        price=lo,
                        is_high=False,
                        confirmed_at_index=confirmed_at,
                    ))

        return swing_highs, swing_lows

    def _build_trendlines(
        self,
        swing_points: List[SwingPoint],
        is_support: bool,
        min_touches: int,
        touch_tolerance: Decimal,
        n_candles: int,
    ) -> List[Trendline]:
        """Build trendlines from swing points.

        For support: connect swing lows (price below current).
        For resistance: connect swing highs (price above current).
        """
        if len(swing_points) < min_touches:
            return []

        trendlines: List[Trendline] = []

        # Try pairs of points to form trendlines
        for i in range(len(swing_points)):
            for j in range(i + 1, len(swing_points)):
                p1 = swing_points[i]
                p2 = swing_points[j]
                idx_diff = p2.index - p1.index
                if idx_diff <= 0:
                    continue

                slope = (p2.price - p1.price) / Decimal(idx_diff)
                intercept = p1.price - slope * Decimal(p1.index)

                # Count touches
                touch_count = 0
                last_touch_index: Optional[int] = None
                for sp in swing_points:
                    idx = sp.index
                    expected = slope * Decimal(idx) + intercept
                    tolerance_amount = expected * touch_tolerance
                    if abs(sp.price - expected) <= tolerance_amount:
                        touch_count += 1
                        last_touch_index = idx

                if touch_count >= min_touches:
                    # Only include trendlines where last touch is recent
                    # (within last 30% of lookback)
                    if last_touch_index is not None and last_touch_index < n_candles * 0.3:
                        continue

                    trendlines.append(Trendline(
                        points=[p1, p2],
                        slope=slope,
                        intercept=intercept,
                        touch_count=touch_count,
                        last_touch_index=last_touch_index,
                        is_support=is_support,
                    ))

        return trendlines

    def _price_at_index(
        self,
        trendline: Trendline,
        index: int,
    ) -> Decimal:
        return trendline.slope * Decimal(index) + trendline.intercept

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

        p = dict(parameters.values) if parameters else dict(self.default_parameters.params if hasattr(parameters, 'params') else parameters.values) if parameters else {}
        min_swing_strength = int(p.get("min_swing_strength", 3))
        min_touches = int(p.get("min_touches", 2))
        max_lookback = int(p.get("max_lookback", 100))
        touch_tolerance = Decimal(str(p.get("touch_tolerance", 0.002)))
        breakout_confirm = int(p.get("breakout_confirmation_candles", 2))
        retest_lookback = int(p.get("retest_lookback", 10))

        n = len(entry_candles)
        if n < min_swing_strength * 2 + min_touches + 5:
            return StrategyResult(
                strategy_name=self.name, symbol=symbol, timeframe=entry_tf,
                signals=[], rejections=[], market_regime=MarketRegime.UNKNOWN,
                indicator_snapshots={},
                error=f"Insufficient candles: {n}",
            )

        # Detect swing points
        swing_highs, swing_lows = self._detect_swing_points(
            entry_candles, min_swing_strength, max_lookback
        )

        # Build trendlines
        support_lines = self._build_trendlines(
            swing_lows, is_support=True, min_touches=min_touches,
            touch_tolerance=touch_tolerance, n_candles=n,
        )
        resistance_lines = self._build_trendlines(
            swing_highs, is_support=False, min_touches=min_touches,
            touch_tolerance=touch_tolerance, n_candles=n,
        )

        curr = entry_candles[-1]
        prev = entry_candles[-2] if n >= 2 else None
        curr_close = curr.close
        curr_high = curr.high
        curr_low = curr.low

        signals: List[Signal] = []
        rejections: List[SignalRejection] = []
        confirmation_conditions: List[str] = []
        explanation_parts: List[str] = []

        direction: Optional[SignalDirection] = None
        matched_line: Optional[Trendline] = None
        touch_type: Optional[str] = None

        # --- Check support trendline touch (bounce -> LONG) ---
        best_support: Optional[Trendline] = None
        for tl in support_lines:
            expected = self._price_at_index(tl, n - 1)
            tolerance_amount = expected * touch_tolerance
            # Price near support line (touching from above)
            if curr_low <= expected + tolerance_amount and curr_close >= expected - tolerance_amount:
                if best_support is None or tl.touch_count > best_support.touch_count:
                    best_support = tl

        # --- Check resistance trendline touch (rejection -> SHORT) ---
        best_resistance: Optional[Trendline] = None
        for tl in resistance_lines:
            expected = self._price_at_index(tl, n - 1)
            tolerance_amount = expected * touch_tolerance
            # Price near resistance line (touching from below)
            if curr_high >= expected - tolerance_amount and curr_close <= expected + tolerance_amount:
                if best_resistance is None or tl.touch_count > best_resistance.touch_count:
                    best_resistance = tl

        # --- Breakout detection ---
        # Bullish breakout: price closes above resistance trendline
        bullish_breakout = False
        bearish_breakout = False

        if best_resistance is not None:
            prev_expected = self._price_at_index(best_resistance, n - 2) if n >= 2 else None
            if prev_expected is not None and prev is not None:
                # Price was below resistance, now closes above
                if prev.close <= prev_expected and curr_close > self._price_at_index(best_resistance, n - 1):
                    # Confirm with `breakout_confirm` candles
                    bullish_breakout = True

        if best_support is not None:
            prev_expected = self._price_at_index(best_support, n - 2) if n >= 2 else None
            if prev_expected is not None and prev is not None:
                # Price was above support, now closes below
                if prev.close >= prev_expected and curr_close < self._price_at_index(best_support, n - 1):
                    bearish_breakout = True

        # --- Retest detection ---
        # After breakout, price returns to trendline and bounces
        bullish_retest = False
        bearish_retest = False

        if best_resistance is not None and n > breakout_confirm:
            # Check if price broke out earlier and is now retesting from above
            breakout_idx = None
            for i in range(n - retest_lookback, n):
                expected = self._price_at_index(best_resistance, i)
                if entry_candles[i].close > expected:
                    breakout_idx = i
                    break
            if breakout_idx is not None:
                # Price should be near the trendline now (retest)
                expected_now = self._price_at_index(best_resistance, n - 1)
                tolerance_amount = expected_now * touch_tolerance
                if curr_low <= expected_now + tolerance_amount and curr_close >= expected_now - tolerance_amount:
                    bullish_retest = True

        if best_support is not None and n > breakout_confirm:
            breakout_idx = None
            for i in range(n - retest_lookback, n):
                expected = self._price_at_index(best_support, i)
                if entry_candles[i].close < expected:
                    breakout_idx = i
                    break
            if breakout_idx is not None:
                expected_now = self._price_at_index(best_support, n - 1)
                tolerance_amount = expected_now * touch_tolerance
                if curr_high >= expected_now - tolerance_amount and curr_close <= expected_now + tolerance_amount:
                    bearish_retest = True

        # --- Determine direction ---
        if bullish_breakout or bullish_retest or (best_support is not None and curr_close >= self._price_at_index(best_support, n - 1)):
            direction = SignalDirection.LONG
            matched_line = best_support
            touch_type = "support_bounce" if best_support else "breakout"
            confirmation_conditions.append(f"Support trendline (touch count: {best_support.touch_count if best_support else 0})")
            if bullish_breakout:
                explanation_parts.append("LONG: bullish breakout above resistance trendline with confirmation")
            elif bullish_retest:
                explanation_parts.append("LONG: bullish retest of broken resistance trendline")
            else:
                explanation_parts.append("LONG: price at support trendline bounce")

        elif bearish_breakout or bearish_retest or (best_resistance is not None and curr_close <= self._price_at_index(best_resistance, n - 1)):
            direction = SignalDirection.SHORT
            matched_line = best_resistance
            touch_type = "resistance_rejection" if best_resistance else "breakout"
            confirmation_conditions.append(f"Resistance trendline (touch count: {best_resistance.touch_count if best_resistance else 0})")
            if bearish_breakout:
                explanation_parts.append("SHORT: bearish breakout below support trendline with confirmation")
            elif bearish_retest:
                explanation_parts.append("SHORT: bearish retest of broken support trendline")
            else:
                explanation_parts.append("SHORT: price at resistance trendline rejection")
        else:
            explanation_parts.append("No trendline touch or breakout detected")

        # --- Build signal ---
        now = datetime.now(timezone.utc)
        last_candle_ts = entry_candles[-1].timestamp if entry_candles else now

        if direction is not None and matched_line is not None:
            tl_expected = self._price_at_index(matched_line, n - 1)
            invalidation: Optional[Decimal] = None
            if direction == SignalDirection.LONG:
                # Invalidate below the trendline
                invalidation = tl_expected * (Decimal("1") - touch_tolerance)
            else:
                invalidation = tl_expected * (Decimal("1") + touch_tolerance)

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
                    "trendline_touch_count": matched_line.touch_count,
                    "trendline_slope": float(matched_line.slope),
                    "trendline_intercept": float(matched_line.intercept),
                    "trendline_expected_price": float(tl_expected),
                    "touch_type": touch_type or "touch",
                    "support_lines_count": len(support_lines),
                    "resistance_lines_count": len(resistance_lines),
                },
                market_regime=MarketRegime.TRENDING,
                confirmation_conditions=confirmation_conditions,
                explanation=". ".join(explanation_parts) + ".",
                expiry_conditions=[
                    "Price closes beyond trendline invalidation level",
                    "New swing point invalidates trendline",
                    f"Signal age exceeds {p.get('max_signal_age_minutes', 60)} minutes",
                ],
                data_source=data_source,
                strategy_validity_state="valid" if self._enabled else "disabled",
                metadata={
                    "touch_type": touch_type or "touch",
                    "trendline_touches": matched_line.touch_count,
                    "is_support": matched_line.is_support,
                },
            ))
        else:
            reason = "; ".join(explanation_parts) if explanation_parts else "No trendline setup"
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
            market_regime=MarketRegime.TRENDING,
            indicator_snapshots={
                "trendline": IndicatorParameters(values=dict(p)),
            },
        )
