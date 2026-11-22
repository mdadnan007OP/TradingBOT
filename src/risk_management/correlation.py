"""Correlation-aware exposure management.

Computes historical return correlation between instruments, detects highly
correlated existing positions, and assesses combined exposure. Statistical
correlation is NOT a guarantee of future relationships.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional

from src.risk_management.config import RiskPolicy
from src.risk_management.models import CorrelationResult


@dataclass(frozen=True)
class CorrelationInput:
    candidate_symbol: str
    position_symbols: List[str]
    returns: Dict[str, List[Decimal]]  # symbol -> historical returns
    window: int
    min_data_points: int


def pearson_correlation(
    x: List[Decimal],
    y: List[Decimal],
) -> Optional[Decimal]:
    """Pearson correlation coefficient between two return series.

    Returns None if insufficient or invalid data.
    """
    n = min(len(x), len(y))
    if n < 2:
        return None
    x_vals = [float(v) for v in x[-n:]]
    y_vals = [float(v) for v in y[-n:]]

    mean_x = sum(x_vals) / n
    mean_y = sum(y_vals) / n

    num = sum((a - mean_x) * (b - mean_y) for a, b in zip(x_vals, y_vals))
    den_x = sum((a - mean_x) ** 2 for a in x_vals) ** 0.5
    den_y = sum((b - mean_y) ** 2 for b in y_vals) ** 0.5

    if den_x == 0 or den_y == 0:
        return None

    coeff = num / (den_x * den_y)
    # Clamp to [-1, 1] to correct floating point drift.
    coeff = max(-1.0, min(1.0, coeff))
    return Decimal(str(coeff))


def evaluate_correlation(
    candidate_symbol: str,
    position_symbols: List[str],
    returns: Dict[str, List[Decimal]],
    policy: RiskPolicy,
) -> CorrelationResult:
    """Evaluate correlation of candidate against existing positions.

    Does not reject solely on noisy/insufficient data unless policy requires.
    """
    threshold = policy.max_correlation_threshold
    window = policy.correlation_window
    min_points = policy.min_correlation_data_points

    correlated: List[str] = []
    max_corr: Optional[Decimal] = None
    total = Decimal("0")
    count = 0
    sufficient = False
    breach = False
    reason: Optional[str] = None

    candidate_returns = returns.get(candidate_symbol, [])
    recent_candidate = candidate_returns[-window:] if window else candidate_returns

    for sym in position_symbols:
        if sym == candidate_symbol:
            continue
        sym_returns = returns.get(sym, [])
        recent_sym = sym_returns[-window:] if window else sym_returns
        if len(recent_candidate) < min_points or len(recent_sym) < min_points:
            continue
        sufficient = True
        coeff = pearson_correlation(recent_candidate, recent_sym)
        if coeff is None:
            continue
        count += 1
        total += abs(coeff)
        if max_corr is None or abs(coeff) > abs(max_corr):
            max_corr = coeff
        if threshold is not None and abs(coeff) >= abs(threshold):
            correlated.append(sym)
            breach = True

    avg_corr = (total / count) if count > 0 else None

    if not sufficient:
        reason = (
            f"Insufficient correlation data (need >= {min_points} points); "
            "correlation not used for rejection"
        )
    elif breach:
        reason = (
            f"Highly correlated positions detected: {', '.join(correlated)} "
            f"(max |correlation| = {max_corr})"
        )

    return CorrelationResult(
        candidate_symbol=candidate_symbol,
        correlated_symbols=correlated,
        max_correlation=max_corr,
        average_correlation=avg_corr,
        window_used=window,
        data_points=len(recent_candidate),
        sufficient_data=sufficient,
        breach=breach,
        reason=reason,
    )
