"""Drawdown analysis.

Computes maximum drawdown, drawdown duration (time under water), recovery
factor and related metrics from an equity curve.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from src.backtesting.equity_curve import (
    build_equity_curve,
    compute_drawdown_series,
    max_drawdown,
    to_float,
)
from src.backtesting.models import EquityPoint


@dataclass
class DrawdownAnalysis:
    max_drawdown_percent: float
    max_drawdown_amount: float
    max_drawdown_duration: Optional[float]
    """Seconds spent in the deepest drawdown (under water)."""
    average_drawdown_percent: float
    recovery_factor: Optional[float]
    """Net profit / max drawdown."""
    time_under_water_percent: float
    """Fraction of the equity curve spent below a previous peak."""


def analyze_drawdown(points: List[EquityPoint]) -> DrawdownAnalysis:
    curve = build_equity_curve(points)
    if not curve:
        return DrawdownAnalysis(0.0, 0.0, None, 0.0, None, 0.0)

    equities = [c.equity for c in curve]
    dd_series = compute_drawdown_series(equities)
    max_dd = max(dd_series) if dd_series else 0.0

    # Peak equity amount at max drawdown.
    peak = equities[0]
    peak_at_max = peak
    running_peak = equities[0]
    max_amount = 0.0
    for eq in equities:
        if eq > running_peak:
            running_peak = eq
        dd_amount = running_peak - eq
        if dd_amount > max_amount:
            max_amount = dd_amount
            peak_at_max = running_peak

    # Longest time under water (consecutive points with dd > 0).
    longest_under_water = 0.0
    current_start: Optional[datetime] = None
    for i, dd in enumerate(dd_series):
        if dd > 0:
            if current_start is None:
                current_start = curve[i].timestamp
            duration = (curve[i].timestamp - current_start).total_seconds()
            if duration > longest_under_water:
                longest_under_water = duration
        else:
            current_start = None

    avg_dd = sum(dd_series) / len(dd_series) if dd_series else 0.0

    net_profit = equities[-1] - equities[0]
    recovery_factor = (net_profit / max_amount) if max_amount > 0 else None

    time_under_water = (
        sum(1 for dd in dd_series if dd > 0) / len(dd_series) if dd_series else 0.0
    )

    return DrawdownAnalysis(
        max_drawdown_percent=max_dd * 100.0,
        max_drawdown_amount=max_amount,
        max_drawdown_duration=longest_under_water if longest_under_water > 0 else None,
        average_drawdown_percent=avg_dd * 100.0,
        recovery_factor=recovery_factor,
        time_under_water_percent=time_under_water * 100.0,
    )