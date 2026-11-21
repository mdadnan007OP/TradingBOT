"""Daily High / Low Strategy.

Identifies breakouts and rejections of:
    * Previous day high / low (daily granularity)
    * Current session high / low
    * Previous week high / low (weekly granularity)

Uses the existing market-session infrastructure. Does not assume uniform
daily session boundaries across markets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
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
class PeriodLevels:
    """High/low levels for a completed period."""

    period_start: datetime
    period_end: datetime
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass(frozen=True)
class DailyHighLowParameters:
    """Parameters for Daily High / Low Strategy."""

    use_previous_day: bool = True
    use_previous_week: bool = True
    breakout_confirmation_candles: int = 2
    retest_lookback: int = 10
    price_tolerance: Decimal = Decimal("0.001")
    min_breakout_distance: Decimal = Decimal("0.001")


class DailyHighLowStrategy(Strategy):
    """Daily/Weekly High-Low breakout and rejection strategy."""

    name = "DailyHighLow"
    version = "1.0.0"

    def __init__(self) -> None:
        self._enabled = True
        self._params = DailyHighLowParameters()

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
            "use_previous_day": self._params.use_previous_day,
            "use_previous_week": self._params.use_previous_week,
            "breakout_confirmation_candles": self._params.breakout_confirmation_candles,
            "retest_lookback": self._params.retest_lookback,
            "price_tolerance": float(self._params.price_tolerance),
            "min_breakout_distance": float(self._params.min_breakout_distance),
        })

    def validate_parameters(self, parameters: IndicatorParameters) -> IndicatorParameters:
        values = dict(parameters.values)
        confirm = int(values.get("breakout_confirmation_candles", 2))
        if confirm < 1:
            raise ValueError("breakout_confirmation_candles must be >= 1")
        return IndicatorParameters(values=values)

    # ------------------------------------------------------------------
    # Period aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def _period_start_for_day(ts: datetime) -> datetime:
        """Return the start of the UTC day containing ts."""
        return ts.replace(hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def _period_start_for_week(ts: datetime) -> datetime:
        """Return the start of the ISO week (Monday) containing ts."""
        day = ts.weekday()  # Monday = 0
        start = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        return start - timedelta(days=day)

    def _aggregate_periods(
        self,
        candles: List[OHLCBar],
        granularity: str,  # "daily" or "weekly"
    ) -> List[PeriodLevels]:
        """Aggregate candles into completed periods with H/L/C."""
        periods: List[PeriodLevels] = []
        current_key: Optional[datetime] = None
        current_high: Optional[Decimal] = None
        current_low: Optional[Decimal] = None
        current_close: Optional[Decimal] = None
        current_start: Optional[datetime] = None

        for c in candles:
            if granularity == "daily":
                key = self._period_start_for_day(c.timestamp)
            else:
                key = self._period_start_for_week(c.timestamp)

            if current_key is None or key != current_key:
                # Save previous period
                if current_key is not None and current_high is not None:
                    periods.append(PeriodLevels(
                        period_start=current_start or current_key,
                        period_end=current_key,
                        high=current_high,
                        low=current_low,
                        close=current_close or Decimal("0"),
                    ))
                current_key = key
                current_start = key
                current_high = c.high
                current_low = c.low
                current_close = c.close
            else:
                if current_high is None or c.high > current_high:
                    current_high = c.high
                if current_low is None or c.low < current_low:
                    current_low = c.low
                current_close = c.close

        # Don't append the current (incomplete) period
        return periods

    def _get_levels(
        self,
        periods: List[PeriodLevels],
        index_from_end: int,
    ) -> Optional[PeriodLevels]:
        """Get period levels by index from end (-1 = most recent completed)."""
        if index_from_end >= len(periods):
            return None
        return periods[-(index_from_end + 1)]

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
        use_prev_day = bool(p.get("use_previous_day", True))
        use_prev_week = bool(p.get("use_previous_week", True))
        confirm = int(p.get("breakout_confirmation_candles", 2))
        retest_lb = int(p.get("retest_lookback", 10))
        price_tol = Decimal(str(p.get("price_tolerance", 0.001)))
        min_breakout_dist = Decimal(str(p.get("min_breakout_distance", 0.001)))

        n = len(entry_candles)
        if n < 3:
            return StrategyResult(
                strategy_name=self.name, symbol=symbol, timeframe=entry_tf,
                signals=[], rejections=[], market_regime=MarketRegime.UNKNOWN,
                indicator_snapshots={},
                error=f"Insufficient candles: {n}",
            )

        curr = entry_candles[-1]
        prev = entry_candles[-2] if n >= 2 else None
        curr_close = curr.close
        curr_high = curr.high
        curr_low = curr.low

        # Aggregate daily periods
        daily_periods = self._aggregate_periods(entry_candles, "daily")
        weekly_periods = self._aggregate_periods(entry_candles, "weekly")

        signals: List[Signal] = []
        rejections: List[SignalRejection] = []
        confirmation_conditions: List[str] = []
        explanation_parts: List[str] = []

        direction: Optional[SignalDirection] = None
        reference_level: Optional[Decimal] = None
        level_type: Optional[str] = None
        invalidation: Optional[Decimal] = None

        # --- Previous Day High / Low ---
        if use_prev_day and len(daily_periods) >= 2:
            prev_day = self._get_levels(daily_periods, 1)  # Most recent completed
            curr_day = self._get_levels(daily_periods, 0)  # Current (may be incomplete)

            if prev_day is not None:
                prev_day_high = prev_day.high
                prev_day_low = prev_day.low

                # Bullish breakout above previous day high
                if prev is not None and prev.close <= prev_day_high and curr_close > prev_day_high:
                    # Confirm with `confirm` candles above
                    breakout_confirmed = True
                    for i in range(max(0, n - confirm), n):
                        if entry_candles[i].close <= prev_day_high:
                            breakout_confirmed = False
                            break
                    if breakout_confirmed:
                        direction = SignalDirection.LONG
                        reference_level = prev_day_high
                        level_type = "previous_day_high"
                        confirmation_conditions.append(
                            f"Breakout above previous day high ({prev_day_high})"
                        )
                        explanation_parts.append(
                            f"LONG: breakout above previous day high {prev_day_high}"
                        )
                        invalidation = prev_day_high * (Decimal("1") - price_tol)

                # Bearish breakout below previous day low
                if direction is None and prev is not None and prev.close >= prev_day_low and curr_close < prev_day_low:
                    breakout_confirmed = True
                    for i in range(max(0, n - confirm), n):
                        if entry_candles[i].close >= prev_day_low:
                            breakout_confirmed = False
                            break
                    if breakout_confirmed:
                        direction = SignalDirection.SHORT
                        reference_level = prev_day_low
                        level_type = "previous_day_low"
                        confirmation_conditions.append(
                            f"Breakout below previous day low ({prev_day_low})"
                        )
                        explanation_parts.append(
                            f"SHORT: breakout below previous day low {prev_day_low}"
                        )
                        invalidation = prev_day_low * (Decimal("1") + price_tol)

                # Rejection at previous day high (price touches high, closes below)
                if direction is None and curr_high >= prev_day_high * (Decimal("1") - price_tol) and curr_close < prev_day_high:
                    direction = SignalDirection.SHORT
                    reference_level = prev_day_high
                    level_type = "previous_day_high_rejection"
                    confirmation_conditions.append(
                        f"Rejection at previous day high ({prev_day_high})"
                    )
                    explanation_parts.append(
                        f"SHORT: rejection at previous day high {prev_day_high}"
                    )
                    invalidation = prev_day_high * (Decimal("1") + price_tol)

                # Rejection at previous day low (price touches low, closes above)
                if direction is None and curr_low <= prev_day_low * (Decimal("1") + price_tol) and curr_close > prev_day_low:
                    direction = SignalDirection.LONG
                    reference_level = prev_day_low
                    level_type = "previous_day_low_rejection"
                    confirmation_conditions.append(
                        f"Rejection at previous day low ({prev_day_low})"
                    )
                    explanation_parts.append(
                        f"LONG: rejection at previous day low {prev_day_low}"
                    )
                    invalidation = prev_day_low * (Decimal("1") - price_tol)

        # --- Previous Week High / Low ---
        if direction is None and use_prev_week and len(weekly_periods) >= 2:
            prev_week = self._get_levels(weekly_periods, 1)

            if prev_week is not None:
                prev_week_high = prev_week.high
                prev_week_low = prev_week.low

                if prev is not None and prev.close <= prev_week_high and curr_close > prev_week_high:
                    direction = SignalDirection.LONG
                    reference_level = prev_week_high
                    level_type = "previous_week_high"
                    confirmation_conditions.append(
                        f"Breakout above previous week high ({prev_week_high})"
                    )
                    explanation_parts.append(
                        f"LONG: breakout above previous week high {prev_week_high}"
                    )
                    invalidation = prev_week_high * (Decimal("1") - price_tol)

                if direction is None and prev is not None and prev.close >= prev_week_low and curr_close < prev_week_low:
                    direction = SignalDirection.SHORT
                    reference_level = prev_week_low
                    level_type = "previous_week_low"
                    confirmation_conditions.append(
                        f"Breakout below previous week low ({prev_week_low})"
                    )
                    explanation_parts.append(
                        f"SHORT: breakout below previous week low {prev_week_low}"
                    )
                    invalidation = prev_week_low * (Decimal("1") + price_tol)

        if direction is None:
            explanation_parts.append("No daily/weekly high-low breakout or rejection")

        # --- Build signal ---
        now = datetime.now(timezone.utc)
        last_candle_ts = entry_candles[-1].timestamp if entry_candles else now

        if direction is not None and reference_level is not None:
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
                    "reference_level": float(reference_level),
                    "level_type": level_type or "unknown",
                    "daily_periods_count": len(daily_periods),
                    "weekly_periods_count": len(weekly_periods),
                    "prev_day_high": float(daily_periods[-2].high) if len(daily_periods) >= 2 else None,
                    "prev_day_low": float(daily_periods[-2].low) if len(daily_periods) >= 2 else None,
                    "prev_week_high": float(weekly_periods[-2].high) if len(weekly_periods) >= 2 else None,
                    "prev_week_low": float(weekly_periods[-2].low) if len(weekly_periods) >= 2 else None,
                },
                market_regime=MarketRegime.TRANSITIONING,
                confirmation_conditions=confirmation_conditions,
                explanation=". ".join(explanation_parts) + ".",
                expiry_conditions=[
                    f"Price closes beyond invalidation level ({invalidation})",
                    "New daily/weekly period begins",
                    f"Signal age exceeds {p.get('max_signal_age_minutes', 60)} minutes",
                ],
                data_source=data_source,
                strategy_validity_state="valid" if self._enabled else "disabled",
                metadata={
                    "level_type": level_type or "unknown",
                    "reference_level": float(reference_level),
                    "use_previous_day": use_prev_day,
                    "use_previous_week": use_prev_week,
                },
            ))
        else:
            reason = "; ".join(explanation_parts) if explanation_parts else "No daily/weekly level setup"
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
                "daily_high_low": IndicatorParameters(values=dict(p)),
            },
        )
