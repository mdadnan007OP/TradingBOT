"""Signal conflict detection and aggregation.

Multiple strategies may generate different signals for the same instrument.
This component detects conflicts, identifies agreement groups, and provides
configurable aggregation policies without forcing trade decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.strategies.base import (
    Signal,
    SignalDirection,
    SignalStatus,
    StrategyResult,
)


@dataclass(frozen=True)
class SignalConflict:
    """A detected conflict between strategies."""

    symbol: str
    timeframe: str
    conflicting_strategies: List[str]
    """Strategy names on opposite sides."""

    long_strategies: List[str]
    short_strategies: List[str]

    long_count: int
    short_count: int

    resolution: str
    """How the conflict was handled (e.g. 'reported', 'consensus_required')."""

    explanation: str


@dataclass(frozen=True)
class ConflictDetectionResult:
    """Result of conflict detection."""

    has_conflicts: bool
    conflicts: List[SignalConflict]
    agreement_groups: List[List[str]]
    """Groups of strategies that agree on the same direction."""

    aggregated_direction: Optional[SignalDirection]
    """Aggregated direction, or None if unresolved."""

    confidence: Decimal
    """Confidence in the aggregation (0-100)."""

    explanation: str


class SignalConflictResolver:
    """Detects and resolves signal conflicts across strategies."""

    def __init__(self) -> None:
        pass

    def detect(self, results: List[StrategyResult]) -> Dict[str, Any]:
        """Detect conflicts across strategy results.

        Returns a dict suitable for JSON serialization with:
            * has_conflicts
            * conflicts (list)
            * agreement_groups (list of strategy name lists)
            * aggregated_direction
            * confidence
            * explanation
        """
        # Collect active signals by direction
        long_strategies: List[str] = []
        short_strategies: List[str] = []
        none_strategies: List[str] = []
        signal_details: List[Dict[str, Any]] = []

        for result in results:
            if result.error:
                continue
            for sig in result.active_signals:
                signal_details.append(
                    {
                        "strategy": result.strategy_name,
                        "symbol": sig.symbol,
                        "timeframe": sig.entry_timeframe.value,
                        "direction": sig.direction.value,
                        "confidence": float(sig.metadata.get("confidence", 0)),
                        "explanation": sig.explanation,
                    }
                )
                if sig.direction == SignalDirection.LONG:
                    long_strategies.append(result.strategy_name)
                elif sig.direction == SignalDirection.SHORT:
                    short_strategies.append(result.strategy_name)
                else:
                    none_strategies.append(result.strategy_name)

        # Determine symbols involved
        symbols = set(sd["symbol"] for sd in signal_details)
        timeframes = set(sd["timeframe"] for sd in signal_details)

        conflicts: List[SignalConflict] = []
        for symbol in symbols:
            symbol_long = [
                sd for sd in signal_details
                if sd["symbol"] == symbol and sd["direction"] == "LONG"
            ]
            symbol_short = [
                sd for sd in signal_details
                if sd["symbol"] == symbol and sd["direction"] == "SHORT"
            ]
            if symbol_long and symbol_short:
                conflicts.append(
                    SignalConflict(
                        symbol=symbol,
                        timeframe=timeframes.pop() if timeframes else "M1",
                        conflicting_strategies=list(
                            set(sd["strategy"] for sd in symbol_long + symbol_short)
                        ),
                        long_strategies=list(set(sd["strategy"] for sd in symbol_long)),
                        short_strategies=list(set(sd["strategy"] for sd in symbol_short)),
                        long_count=len(symbol_long),
                        short_count=len(symbol_short),
                        resolution="reported",
                        explanation=(
                            f"Conflict on {symbol}: "
                            f"{len(symbol_long)} LONG ({', '.join(sd['strategy'] for sd in symbol_long)}) "
                            f"vs {len(symbol_short)} SHORT ({', '.join(sd['strategy'] for sd in symbol_short)})"
                        ),
                    )
                )

        # Agreement groups
        agreement_groups: List[List[str]] = []
        if long_strategies:
            agreement_groups.append(sorted(set(long_strategies)))
        if short_strategies:
            agreement_groups.append(sorted(set(short_strategies)))
        if none_strategies:
            agreement_groups.append(sorted(set(none_strategies)))

        # Aggregation
        aggregated_direction: Optional[SignalDirection] = None
        confidence = Decimal("0")
        explanation_parts: List[str] = []

        if long_strategies and not short_strategies:
            aggregated_direction = SignalDirection.LONG
            confidence = Decimal("90")
            explanation_parts.append(
                f"Unanimous LONG from {len(long_strategies)} strategy(ies)"
            )
        elif short_strategies and not long_strategies:
            aggregated_direction = SignalDirection.SHORT
            confidence = Decimal("90")
            explanation_parts.append(
                f"Unanimous SHORT from {len(short_strategies)} strategy(ies)"
            )
        elif long_strategies and short_strategies:
            # Conflict — no forced direction
            total = len(long_strategies) + len(short_strategies)
            long_pct = Decimal(len(long_strategies)) / Decimal(total) * Decimal("100")
            short_pct = Decimal(len(short_strategies)) / Decimal(total) * Decimal("100")
            confidence = Decimal("50")
            explanation_parts.append(
                f"Conflict: {long_pct:.0f}% LONG / {short_pct:.0f}% SHORT "
                f"({total} strategies). No forced direction."
            )
        else:
            explanation_parts.append("No active signals from any strategy")

        return {
            "has_conflicts": len(conflicts) > 0,
            "conflicts": [
                {
                    "symbol": c.symbol,
                    "timeframe": c.timeframe,
                    "conflicting_strategies": c.conflicting_strategies,
                    "long_strategies": c.long_strategies,
                    "short_strategies": c.short_strategies,
                    "long_count": c.long_count,
                    "short_count": c.short_count,
                    "resolution": c.resolution,
                    "explanation": c.explanation,
                }
                for c in conflicts
            ],
            "agreement_groups": agreement_groups,
            "aggregated_direction": (
                aggregated_direction.value if aggregated_direction else None
            ),
            "confidence": float(confidence),
            "explanation": "; ".join(explanation_parts),
            "signal_details": signal_details,
        }

    def aggregate(
        self,
        results: List[StrategyResult],
        policy: str = "report_conflicts",
    ) -> Dict[str, Any]:
        """Aggregate signals using the specified policy.

        Policies:
            * "report_conflicts" — return all signals with conflict annotations
            * "consensus" — require all strategies to agree on a direction
            * "majority" — direction with most supporting strategies
            * "unanimous" — only if all strategies agree
        """
        detection = self.detect(results)

        if policy == "report_conflicts":
            return {
                "policy": "report_conflicts",
                "has_conflicts": detection["has_conflicts"],
                "conflicts": detection["conflicts"],
                "agreement_groups": detection["agreement_groups"],
                "aggregated_direction": detection["aggregated_direction"],
                "confidence": detection["confidence"],
                "explanation": detection["explanation"],
                "signal_details": detection["signal_details"],
                "decision": "REPORT_CONFLICTS",
            }

        if policy == "unanimous":
            if detection["has_conflicts"]:
                return {
                    "policy": "unanimous",
                    "decision": "NO_CONSENSUS",
                    "reason": "Strategies disagree — unanimous policy not satisfied",
                    **detection,
                }
            direction = detection["aggregated_direction"]
            if direction is None:
                return {
                    "policy": "unanimous",
                    "decision": "NO_SIGNAL",
                    "reason": "No active signals",
                    **detection,
                }
            return {
                "policy": "unanimous",
                "decision": "SIGNAL",
                "direction": direction,
                "confidence": detection["confidence"],
                **detection,
            }

        if policy == "consensus":
            # All strategies that produce a signal must agree
            if detection["has_conflicts"]:
                return {
                    "policy": "consensus",
                    "decision": "NO_CONSENSUS",
                    "reason": "Strategies disagree — consensus policy not satisfied",
                    **detection,
                }
            direction = detection["aggregated_direction"]
            if direction is None:
                return {
                    "policy": "consensus",
                    "decision": "NO_SIGNAL",
                    "reason": "No active signals",
                    **detection,
                }
            return {
                "policy": "consensus",
                "decision": "SIGNAL",
                "direction": direction,
                "confidence": detection["confidence"],
                **detection,
            }

        if policy == "majority":
            long_count = detection["conflicts"][0]["long_count"] if detection["conflicts"] else 0
            short_count = detection["conflicts"][0]["short_count"] if detection["conflicts"] else 0
            # Recalculate from signal_details
            long_count = sum(
                1 for sd in detection["signal_details"] if sd["direction"] == "LONG"
            )
            short_count = sum(
                1 for sd in detection["signal_details"] if sd["direction"] == "SHORT"
            )
            if long_count > short_count:
                return {
                    "policy": "majority",
                    "decision": "SIGNAL",
                    "direction": SignalDirection.LONG.value,
                    "confidence": detection["confidence"],
                    **detection,
                }
            elif short_count > long_count:
                return {
                    "policy": "majority",
                    "decision": "SIGNAL",
                    "direction": SignalDirection.SHORT.value,
                    "confidence": detection["confidence"],
                    **detection,
                }
            return {
                "policy": "majority",
                "decision": "NO_SIGNAL",
                "reason": "Tie — no majority",
                **detection,
            }

        # Unknown policy — default to report_conflicts
        return {
            "policy": "report_conflicts",
            "decision": "UNKNOWN_POLICY",
            "reason": f"Unknown aggregation policy '{policy}'",
            **detection,
        }
