"""Liquidity Hunting Strategy.

Detects price-based liquidity sweeps (NOT confirmed institutional order flow):
    * Equal highs / equal lows
    * Previous swing highs / lows
    * Liquidity sweeps (false breakouts)
    * Sweep and close-back-inside patterns

Requires appropriate candle-close confirmation. Uses configurable price
tolerance, minimum swing strength, and lookback periods.

IMPORTANT: OHLC data cannot prove the presence of actual resting institutional
orders. These are price-based liquidity proxies only.
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
class LiquidityHuntingParameters:
    """Parameters for Liquidity Hunting Strategy."""

    price_tolerance: Decimal = Decimal("0.001")  # 0.1% tolerance for equal highs/lows
    min_swing_strength: int = 3                   # candles to confirm swing point
    lookback_periods: int = 50                    # lookback for swing detection
    sweep_confirmation_candles: int = 2           # candles to confirm sweep close-back
    min_sweep_distance: Decimal = Decimal("0.002") # min distance beyond swing (0.2%)
    require_close_back_inside: bool = True        # require price to close back inside
    equal_high_low_lookback: int = 20             # lookback for equal highs/lows


class LiquidityHuntingStrategy(Strategy):
    """Liquidity hunting strategy using price-based liquidity proxies."""

    name = "LiquidityHunting"
    version = "1.0.0"

    def __init__(self) -> None:
        self._enabled = True
        self._params = LiquidityHuntingParameters()

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
            MarketRegime.TRANSITIONING,
            MarketRegime.HIGH_VOLATILITY,
        ]

    @property
    def default_parameters(self) -> IndicatorParameters:
        return IndicatorParameters(values={
            "price_tolerance": float(self._params.price_tolerance),
            "min_swing_strength": self._params.min_swing_strength,
            "lookback_periods": self._params.lookback_periods,
            "sweep_confirmation_candles": self._params.sweep_confirmation_candles,
            "min_sweep_distance": float(self._params.min_sweep_distance),
            "require_close_back_inside": self._params.require_close_back_inside,
            "equal_high_low_lookback": self._params.equal_high_low_lookback,
        })

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        values = dict(parameters.values)
        tol = Decimal(str(values.get("price_tolerance", 0.001)))
        if tol <= Decimal("0"):
            raise ValueError("price_tolerance must be > 0")
        strength = int(values.get("min_swing_strength", 3))
        if strength < 1:
            raise ValueError("min_swing_strength must be >= 1")
        lookback = int(values.get("lookback_periods", 50))
        if lookback < 5:
            raise ValueError("lookback_periods must be >= 5")
        return IndicatorParameters(values=values)

    # ------------------------------------------------------------------
    # Swing detection
    # ------------------------------------------------------------------

    def _find_swing_highs(
        self,
        candles: List[OHLCBar],
        strength: int,
        lookback: int,
    ) -> List[int]:
        """Find swing high indices (candle high is highest in window)."""
        n = len(candles)
        swing_highs: List[int] = []
        for i in range(strength, n - strength):
            is_swing = True
            hi = candles[i].high
            # Check left side
            for j in range(i - strength, i):
                if candles[j].high >= hi:
                    is_swing = False
                    break
            if not is_swing:
                continue
            # Check right side
            for j in range(i + 1, i + strength + 1):
                if j >= n:
                    break
                if candles[j].high >= hi:
                    is_swing = False
                    break
            if is_swing:
                swing_highs.append(i)
        return swing_highs

    def _find_swing_lows(
        self,
        candles: List[OHLCBar],
        strength: int,
        lookback: int,
    ) -> List[int]:
        """Find swing low indices."""
        n = len(candles)
        swing_lows: List[int] = []
        for i in range(strength, n - strength):
            is_swing = True
            lo = candles[i].low
            for j in range(i - strength, i):
                if candles[j].low <= lo:
                    is_swing = False
                    break
            if not is_swing:
                continue
            for j in range(i + 1, i + strength + 1):
                if j >= n:
                    break
                if candles[j].low <= lo:
                    is_swing = False
                    break
            if is_swing:
                swing_lows.append(i)
        return swing_lows

    def _are_equal(
        self,
        price1: Decimal,
        price2: Decimal,
        tolerance: Decimal,
    ) -> bool:
        """Check if two prices are equal within tolerance (relative)."""
        if price1 <= Decimal("0") or price2 <= Decimal("0"):
            return False
        diff = abs(price1 - price2)
        avg = (price1 + price2) / Decimal("2")
        return diff / avg <= tolerance

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
        price_tolerance = Decimal(str(p.get("price_tolerance", 0.001)))
        min_swing_strength = int(p.get("min_swing_strength", 3))
        lookback_periods = int(p.get("lookback_periods", 50))
        sweep_confirmation = int(p.get("sweep_confirmation_candles", 2))
        min_sweep_dist = Decimal(str(p.get("min_sweep_distance", 0.002)))
        require_close_back = bool(p.get("require_close_back_inside", True))
        equal_lookback = int(p.get("equal_high_low_lookback", 20))

        n = len(entry_candles)
        if n < min_swing_strength * 2 + 5:
            return StrategyResult(
                strategy_name=self.name, symbol=symbol, timeframe=entry_tf,
                signals=[], rejections=[], market_regime=MarketRegime.UNKNOWN,
                indicator_snapshots={},
                error=f"Insufficient candles: {n}, need at least {min_swing_strength * 2 + 5}",
            )

        # Find swing highs and lows
        swing_highs = self._find_swing_highs(entry_candles, min_swing_strength, lookback_periods)
        swing_lows = self._find_swing_lows(entry_candles, min_swing_strength, lookback_periods)

        curr = entry_candles[-1]
        prev = entry_candles[-2] if n >= 2 else None
        curr_close = curr.close
        curr_high = curr.high
        curr_low = curr.low

        signals: List[Signal] = []
        rejections: List[SignalRejection] = []
        confirmation_conditions: List[str] = []
        explanation_parts: List[str] = []

        # --- Detect equal highs / equal lows ---
        equal_highs: List[int] = []
        equal_lows: List[int] = []
        recent_highs = swing_highs[-equal_lookback:] if len(swing_highs) >= equal_lookback else swing_highs
        recent_lows = swing_lows[-equal_lookback:] if len(swing_lows) >= equal_lookback else swing_lows

        for i in range(len(recent_highs)):
            for j in range(i + 1, len(recent_highs)):
                if self._are_equal(
                    entry_candles[recent_highs[i]].high,
                    entry_candles[recent_highs[j]].high,
                    price_tolerance,
                ):
                    equal_highs.append(recent_highs[j])

        for i in range(len(recent_lows)):
            for j in range(i + 1, len(recent_lows)):
                if self._are_equal(
                    entry_candles[recent_lows[i]].low,
                    entry_candles[recent_lows[j]].low,
                    price_tolerance,
                ):
                    equal_lows.append(recent_lows[j])

        # --- Detect liquidity sweeps ---
        # Bullish liquidity sweep: price breaks below swing low, then closes back above
        sweep_low_levels: List[Decimal] = []
        for sl in swing_lows:
            swing_low_price = entry_candles[sl].low
            sweep_level = swing_low_price * (Decimal("1") - min_sweep_dist)
            sweep_low_levels.append(sweep_level)

        # Bearish liquidity sweep: price breaks above swing high, then closes back below
        sweep_high_levels: List[Decimal] = []
        for sh in swing_highs:
            swing_high_price = entry_candles[sh].high
            sweep_level = swing_high_price * (Decimal("1") + min_sweep_dist)
            sweep_high_levels.append(sweep_level)

        direction: Optional[SignalDirection] = None
        matched_conditions: List[str] = []
        invalidation: Optional[Decimal] = None

        # Check for bullish liquidity sweep (price swept below lows, closed back inside)
        swept_below = False
        swept_level: Optional[Decimal] = None
        for sl in swing_lows[-5:]:  # Check recent swings
            swing_low_price = entry_candles[sl].low
            # Did price go below this swing low?
            recent_lows = [c.low for c in entry_candles[sl + 1:]] if sl + 1 < n else []
            if recent_lows and min(recent_lows) < swing_low_price * (Decimal("1") - min_sweep_dist):
                swept_below = True
                swept_level = swing_low_price
                break

        # Check for bearish liquidity sweep
        swept_above = False
        swept_high_level: Optional[Decimal] = None
        for sh in swing_highs[-5:]:
            swing_high_price = entry_candles[sh].high
            recent_highs = [c.high for c in entry_candles[sh + 1:]] if sh + 1 < n else []
            if recent_highs and max(recent_highs) > swing_high_price * (Decimal("1") + min_sweep_dist):
                swept_above = True
                swept_high_level = swing_high_price
                break

        # Check close-back-inside confirmation
        close_back_inside_long = False
        close_back_inside_short = False

        if swept_below and require_close_back and prev is not None:
            # Price closed back above the swing low
            if curr_close > swept_level:
                close_back_inside_long = True

        if swept_above and require_close_back and prev is not None:
            if curr_close < swept_high_level:
                close_back_inside_short = True

        # --- Generate signals ---
        if swept_below and close_back_inside_long:
            direction = SignalDirection.LONG
            matched_conditions.append(
                f"Liquidity sweep below swing low {swept_level}, close back inside"
            )
            explanation_parts.append(
                f"LONG: liquidity sweep below swing low, close-back-inside confirmation"
            )
            invalidation = swept_level * (Decimal("1") - min_sweep_dist)

        elif swept_above and close_back_inside_short:
            direction = SignalDirection.SHORT
            matched_conditions.append(
                f"Liquidity sweep above swing high {swept_high_level}, close back inside"
            )
            explanation_parts.append(
                f"SHORT: liquidity sweep above swing high, close-back-inside confirmation"
            )
            invalidation = swept_high_level * (Decimal("1") + min_sweep_dist)

        # Check equal highs/lows as supporting conditions
        if equal_highs:
            explanation_parts.append(f"Equal highs detected at {len(equal_highs)} level(s)")
            confirmation_conditions.append("Equal highs present")
        if equal_lows:
            explanation_parts.append(f"Equal lows detected at {len(equal_lows)} level(s)")
            confirmation_conditions.append("Equal lows present")

        if direction is None:
            if swept_below:
                explanation_parts.append(
                    "Price swept below swing low but did not close back inside"
                )
            if swept_above:
                explanation_parts.append(
                    "Price swept above swing high but did not close back inside"
                )
            if not swept_below and not swept_above:
                explanation_parts.append("No liquidity sweep detected")

        # --- Build signal ---
        now = datetime.now(timezone.utc)
        last_candle_ts = entry_candles[-1].timestamp if entry_candles else now

        if direction is not None:
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
                    "swing_highs": [float(entry_candles[i].high) for i in swing_highs[-10:]],
                    "swing_lows": [float(entry_candles[i].low) for i in swing_lows[-10:]],
                    "equal_highs": [float(entry_candles[i].high) for i in equal_highs],
                    "equal_lows": [float(entry_candles[i].low) for i in equal_lows],
                    "swept_level": float(swept_level) if swept_level else None,
                    "swept_high_level": float(swept_high_level) if swept_high_level else None,
                },
                market_regime=MarketRegime.TRANSITIONING,
                confirmation_conditions=confirmation_conditions,
                explanation=". ".join(explanation_parts) + ".",
                expiry_conditions=[
                    "Price breaks through the invalidation level",
                    "New swing forms in opposite direction",
                    f"Signal age exceeds {p.get('max_signal_age_minutes', 60)} minutes",
                ],
                data_source=data_source,
                strategy_validity_state="valid" if self._enabled else "disabled",
                metadata={
                    "swept_below": swept_below,
                    "swept_above": swept_above,
                    "close_back_inside_long": close_back_inside_long,
                    "close_back_inside_short": close_back_inside_short,
                    "equal_highs_count": len(equal_highs),
                    "equal_lows_count": len(equal_lows),
                    "liquidity_proxy_only": True,  # Explicit marker: not confirmed institutional flow
                },
            ))
        else:
            reason = "; ".join(explanation_parts) if explanation_parts else "No liquidity sweep setup"
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
                "liquidity_hunting": IndicatorParameters(values=dict(p)),
            },
        )
