"""Shared calculation utilities for indicators.

All functions operate on ``List[Optional[Decimal]]`` series aligned with input
candles. Missing values (``None``) propagate conservatively: a window
containing any ``None`` yields ``None`` unless the function explicitly handles
it. This keeps calculations look-ahead safe and never manufactures data.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional, Tuple

from src.market_data.models import MarketTimeframe, OHLCBar


def sma(values: List[Optional[Decimal]], period: int) -> List[Optional[Decimal]]:
    """Simple Moving Average.

    Formula: ``SMA_t = (1/period) * sum(values[t-period+1 .. t])``.

    Returns ``None`` for the first ``period - 1`` positions and for any
    position whose window contains a ``None``.
    """
    if period < 1:
        raise ValueError("SMA period must be >= 1")
    result: List[Optional[Decimal]] = []
    for i in range(len(values)):
        if i < period - 1:
            result.append(None)
            continue
        window = values[i - period + 1 : i + 1]
        if any(v is None for v in window):
            result.append(None)
        else:
            result.append(sum(window) / Decimal(period))
    return result


def ema(
    values: List[Optional[Decimal]], period: int
) -> List[Optional[Decimal]]:
    """Exponential Moving Average.

    Convention:
        - First EMA value (at index ``period - 1``) = SMA of the first
          ``period`` values (standard initialization).
        - Multiplier ``k = 2 / (period + 1)``.
        - Recursive: ``EMA_t = Close_t * k + EMA_{t-1} * (1 - k)``.

    Returns ``None`` for the first ``period - 1`` positions.
    """
    if period < 1:
        raise ValueError("EMA period must be >= 1")
    multiplier = Decimal(2) / Decimal(period + 1)
    result: List[Optional[Decimal]] = []
    prev_ema: Optional[Decimal] = None
    for i, value in enumerate(values):
        if value is None:
            result.append(None)
            prev_ema = None
            continue
        if i < period - 1:
            result.append(None)
            continue
        if i == period - 1:
            window = values[:period]
            if any(v is None for v in window):
                result.append(None)
            else:
                prev_ema = sum(window) / Decimal(period)
                result.append(prev_ema)
        else:
            if prev_ema is None:
                result.append(None)
            else:
                current = value * multiplier + prev_ema * (Decimal(1) - multiplier)
                prev_ema = current
                result.append(current)
    return result


def wilder_smooth(
    values: List[Optional[Decimal]], period: int
) -> List[Optional[Decimal]]:
    """Wilder's smoothing (used by RSI, ATR, ADX).

    Convention:
        - First smoothed value (at index ``period - 1``) = SMA of the first
          ``period`` values.
        - Recursive: ``Smoothed_t = (Smoothed_{t-1} * (period - 1) + Value_t) / period``.

    Returns ``None`` for the first ``period - 1`` positions.
    """
    if period < 1:
        raise ValueError("Wilder smoothing period must be >= 1")
    result: List[Optional[Decimal]] = []
    prev: Optional[Decimal] = None
    for i, value in enumerate(values):
        if value is None:
            result.append(None)
            prev = None
            continue
        if i < period - 1:
            result.append(None)
            continue
        if i == period - 1:
            window = values[:period]
            if any(v is None for v in window):
                result.append(None)
            else:
                prev = sum(window) / Decimal(period)
                result.append(prev)
        else:
            if prev is None:
                result.append(None)
            else:
                current = (prev * Decimal(period - 1) + value) / Decimal(period)
                prev = current
                result.append(current)
    return result


def typical_price(high: Decimal, low: Decimal, close: Decimal) -> Decimal:
    """Typical price = (High + Low + Close) / 3."""
    return (high + low + close) / Decimal(3)


def mean_deviation(values: List[Decimal], period: int, index: int) -> Decimal:
    """Mean deviation of ``values`` over the window ending at ``index``.

    Window = ``values[index-period+1 .. index]``. Returns the average
    absolute deviation from the window mean. Used by CCI.
    """
    window = values[index - period + 1 : index + 1]
    mean = sum(window) / Decimal(len(window))
    return sum(abs(v - mean) for v in window) / Decimal(len(window))


def true_range(
    high: Decimal, low: Decimal, prev_close: Optional[Decimal]
) -> Decimal:
    """True Range = max(High - Low, |High - PrevClose|, |Low - PrevClose|).

    When ``prev_close`` is None (first bar), returns High - Low.
    """
    candidates = [high - low]
    if prev_close is not None:
        candidates.append(abs(high - prev_close))
        candidates.append(abs(low - prev_close))
    return max(candidates)


def standard_deviation(
    values: List[Decimal], period: int, index: int, sample: bool = False
) -> Decimal:
    """Standard deviation over the window ending at ``index``.

    By default uses population standard deviation (divisor = period), which is
    the convention used by Bollinger Bands. Set ``sample=True`` for sample
    standard deviation (divisor = period - 1).
    """
    window = values[index - period + 1 : index + 1]
    mean = sum(window) / Decimal(len(window))
    variance = sum((v - mean) ** 2 for v in window)
    divisor = Decimal(len(window) - 1) if sample and len(window) > 1 else Decimal(len(window))
    if divisor <= 0:
        return Decimal(0)
    return (variance / divisor).sqrt()


def rolling_sum(values: List[Optional[Decimal]], period: int) -> List[Optional[Decimal]]:
    """Rolling sum over a window of ``period``."""
    if period < 1:
        raise ValueError("rolling_sum period must be >= 1")
    result: List[Optional[Decimal]] = []
    for i in range(len(values)):
        if i < period - 1:
            result.append(None)
            continue
        window = values[i - period + 1 : i + 1]
        if any(v is None for v in window):
            result.append(None)
        else:
            result.append(sum(window))
    return result


def align_to_candles(
    candles: List[OHLCBar],
) -> Tuple[List[Decimal], List[Decimal], List[Decimal], List[Decimal], List[Optional[int]], List[Optional[int]]]:
    """Extract OHLC and volume series from candles.

    Returns (opens, highs, lows, closes, tick_volumes, real_volumes).
    """
    opens: List[Decimal] = []
    highs: List[Decimal] = []
    lows: List[Decimal] = []
    closes: List[Decimal] = []
    tick_volumes: List[Optional[int]] = []
    real_volumes: List[Optional[int]] = []
    for c in candles:
        opens.append(c.open)
        highs.append(c.high)
        lows.append(c.low)
        closes.append(c.close)
        tick_volumes.append(c.tick_volume)
        real_volumes.append(c.real_volume)
    return opens, highs, lows, closes, tick_volumes, real_volumes


def timeframe_minutes(timeframe: MarketTimeframe) -> int:
    """Return the length of ``timeframe`` in minutes."""
    return timeframe.minutes


def previous_period_start(
    timestamp: datetime, timeframe: MarketTimeframe
) -> datetime:
    """Return the start of the previous completed period of ``timeframe``.

    Used by Pivot Points to anchor on the previous completed daily/weekly
    period without peeking into the future.
    """
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    minutes = timeframe.minutes
    # Floor timestamp to the timeframe boundary.
    total_minutes = timestamp.hour * 60 + timestamp.minute
    boundary_minute = (total_minutes // minutes) * minutes
    base = timestamp.replace(
        hour=boundary_minute // 60, minute=boundary_minute % 60, second=0, microsecond=0
    )
    # For multi-day timeframes (D1/W1/MN1), also floor to the period start.
    if timeframe == MarketTimeframe.D1:
        base = base.replace(hour=0, minute=0)
    elif timeframe == MarketTimeframe.W1:
        base = base.replace(hour=0, minute=0)
        # Monday is weekday 0.
        base = base - timedelta(days=base.weekday())
    elif timeframe == MarketTimeframe.MN1:
        base = base.replace(day=1, hour=0, minute=0)
    # Move to the previous completed period.
    return base - timedelta(minutes=minutes)
