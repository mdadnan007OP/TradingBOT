"""Equity curve utilities.

Derives equity/balance/drawdown series from the raw equity points recorded by
the engine. Pure functions; no simulation state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from src.backtesting.models import EquityPoint


@dataclass
class CurvePoint:
    timestamp: datetime
    equity: float
    balance: float
    drawdown_pct: float


def to_float(value: Optional[Decimal]) -> float:
    return float(value) if value is not None else 0.0


def build_equity_curve(points: List[EquityPoint]) -> List[CurvePoint]:
    """Convert EquityPoint objects into float curve points."""
    return [
        CurvePoint(
            timestamp=p.timestamp,
            equity=to_float(p.equity),
            balance=to_float(p.balance),
            drawdown_pct=to_float(p.drawdown_percent),
        )
        for p in points
    ]


def compute_drawdown_series(equities: List[float]) -> List[float]:
    """Return the drawdown (as a positive fraction) at each point."""
    series: List[float] = []
    peak = None
    for eq in equities:
        if peak is None or eq > peak:
            peak = eq
        if peak and peak > 0:
            series.append((peak - eq) / peak)
        else:
            series.append(0.0)
    return series


def max_drawdown(equities: List[float]) -> float:
    """Return the maximum drawdown as a positive fraction."""
    series = compute_drawdown_series(equities)
    return max(series) if series else 0.0


def run_max_drawdown(equities: List[float]) -> float:
    return max_drawdown(equities)