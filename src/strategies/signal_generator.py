"""Multi-indicator confirmation engine.

Evaluates ConfirmationRule groups against indicator results and determines
whether enough conditions are satisfied to emit a signal.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from src.indicators.base import IndicatorResult, ReadinessStatus
from src.market_data.models import MarketTimeframe, OHLCBar
from src.strategies.models import ConfirmationCondition, ConfirmationRule


class ConfirmationEvaluator:
    """Evaluates confirmation conditions against indicator results.

    Operators supported:
        * gt: value > threshold
        * lt: value < threshold
        * eq: value == threshold
        * crosses_above: previous <= threshold, current > threshold
        * crosses_below: previous >= threshold, current < threshold
        * between: low <= value <= high (value is a tuple)
    """

    @staticmethod
    def evaluate_condition(
        condition: ConfirmationCondition,
        current: IndicatorResult,
        previous: Optional[IndicatorResult] = None,
    ) -> Tuple[bool, str]:
        """Evaluate one confirmation condition.

        Returns (satisfied, detail_string).
        """
        outputs = current.values.get(condition.output, [])
        if not outputs:
            return False, f"{condition.output} has no values"

        current_val = outputs[-1]
        if current_val is None:
            return False, f"{condition.output} is None (warm-up/insufficient)"

        op = condition.operator.lower()
        ref = condition.value

        if op == "gt":
            satisfied = current_val > Decimal(str(ref))
            detail = f"{condition.output}={current_val} > {ref}"
        elif op == "lt":
            satisfied = current_val < Decimal(str(ref))
            detail = f"{condition.output}={current_val} < {ref}"
        elif op == "eq":
            satisfied = current_val == Decimal(str(ref))
            detail = f"{condition.output}={current_val} == {ref}"
        elif op == "crosses_above":
            if previous is None:
                satisfied = False
                detail = f"{condition.output}: no previous bar for crossover"
            else:
                prev_outputs = previous.values.get(condition.output, [])
                prev_val = prev_outputs[-1] if prev_outputs else None
                if prev_val is None:
                    satisfied = False
                    detail = f"{condition.output}: previous value is None"
                else:
                    satisfied = prev_val <= Decimal(str(ref)) and current_val > Decimal(str(ref))
                    detail = (
                        f"{condition.output}: {prev_val} -> {current_val} "
                        f"(crosses above {ref})"
                    )
        elif op == "crosses_below":
            if previous is None:
                satisfied = False
                detail = f"{condition.output}: no previous bar for crossover"
            else:
                prev_outputs = previous.values.get(condition.output, [])
                prev_val = prev_outputs[-1] if prev_outputs else None
                if prev_val is None:
                    satisfied = False
                    detail = f"{condition.output}: previous value is None"
                else:
                    satisfied = prev_val >= Decimal(str(ref)) and current_val < Decimal(str(ref))
                    detail = (
                        f"{condition.output}: {prev_val} -> {current_val} "
                        f"(crosses below {ref})"
                    )
        elif op == "between":
            if not isinstance(ref, (list, tuple)) or len(ref) != 2:
                satisfied = False
                detail = f"{condition.output}: 'between' requires [low, high]"
            else:
                low_v = Decimal(str(ref[0]))
                high_v = Decimal(str(ref[1]))
                satisfied = low_v <= current_val <= high_v
                detail = (
                    f"{condition.output}={current_val} in [{low_v}, {high_v}]"
                )
        else:
            satisfied = False
            detail = f"{condition.output}: unknown operator '{condition.operator}'"

        return satisfied, detail

    @staticmethod
    def evaluate_rule(
        rule: ConfirmationRule,
        current: IndicatorResult,
        previous: Optional[IndicatorResult] = None,
    ) -> Tuple[bool, int, int, List[str]]:
        """Evaluate a confirmation rule (group of conditions).

        Returns (rule_satisfied, satisfied_count, total_required, details).
        """
        satisfied_count = 0
        details: List[str] = []

        for cond in rule.conditions:
            ok, detail = ConfirmationEvaluator.evaluate_condition(
                cond, current, previous
            )
            details.append(f"[{'OK' if ok else 'FAIL'}] {detail}")
            if ok:
                satisfied_count += 1

        required_conditions = [c for c in rule.conditions if c.required]
        min_required = max(rule.min_required, len(required_conditions))
        total_required = len(rule.conditions)
        rule_satisfied = satisfied_count >= min_required

        return rule_satisfied, satisfied_count, min_required, details

    @staticmethod
    def evaluate_rules(
        rules: List[ConfirmationRule],
        current: IndicatorResult,
        previous: Optional[IndicatorResult] = None,
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        """Evaluate multiple confirmation rules.

        Returns (any_rule_satisfied, rule_results).
        """
        rule_results: List[Dict[str, Any]] = []
        any_satisfied = False

        for rule in rules:
            satisfied, count, min_req, details = ConfirmationEvaluator.evaluate_rule(
                rule, current, previous
            )
            rule_results.append(
                {
                    "rule_name": rule.name,
                    "satisfied": satisfied,
                    "conditions_met": count,
                    "conditions_required": min_req,
                    "weight": rule.weight,
                    "details": details,
                }
            )
            if satisfied:
                any_satisfied = True

        return any_satisfied, rule_results


class SignalGenerator:
    """Generates trading signals from indicator results and confirmation rules.

    Combines multiple confirmation rules with configurable weights and
    minimum confirmation requirements. Does not place orders.
    """

    def __init__(self) -> None:
        self._evaluator = ConfirmationEvaluator()

    def generate(
        self,
        symbol: str,
        entry_timeframe: MarketTimeframe,
        indicator_result: IndicatorResult,
        previous_result: Optional[IndicatorResult],
        confirmation_rules: List[ConfirmationRule],
        min_confirmations: int = 1,
        market_regime: str = "UNKNOWN",
        regime_confidence: Decimal = Decimal("0"),
        parameters: Any = None,
        data_source: str = "simulated",
        explanation_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Evaluate confirmation rules and produce a signal decision.

        Returns a dict with:
            * direction: SignalDirection value
            * satisfied: bool
            * confidence: Decimal
            * rule_results: list of per-rule evaluation dicts
            * explanation: str
            * conditions_met: list of satisfied condition descriptions
        """
        any_satisfied, rule_results = self._evaluator.evaluate_rules(
            confirmation_rules, indicator_result, previous_result
        )

        total_weight = sum(r.get("weight", 1.0) for r in rule_results)
        satisfied_weight = sum(
            r.get("weight", 1.0)
            for r in rule_results
            if r["satisfied"]
        )
        confidence = Decimal("0")
        if total_weight > 0:
            confidence = Decimal(satisfied_weight) / Decimal(total_weight) * Decimal("100")

        # Adjust confidence by regime alignment
        if market_regime != "UNKNOWN":
            confidence = confidence * (Decimal("1") + regime_confidence / Decimal("200"))

        satisfied_count = sum(1 for r in rule_results if r["satisfied"])
        conditions_met: List[str] = []
        for rr in rule_results:
            if rr["satisfied"]:
                conditions_met.extend(rr["details"])

        if not any_satisfied or satisfied_count < min_confirmations:
            direction = "NONE"
            explanation = (
                explanation_override
                or (
                    f"No signal: {satisfied_count}/{len(rule_results)} "
                    f"confirmation rules satisfied (min {min_confirmations}). "
                    f"Regime: {market_regime}"
                )
            )
        else:
            # Determine direction from indicator snapshot
            direction = self._infer_direction(
                indicator_result, rule_results, explanation_override
            )
            explanation = (
                explanation_override
                or (
                    f"Signal generated: {satisfied_count}/{len(rule_results)} "
                    f"rules satisfied. Regime: {market_regime} "
                    f"(confidence {confidence:.1f}%)."
                )
            )

        return {
            "direction": direction,
            "satisfied": any_satisfied and satisfied_count >= min_confirmations,
            "confidence": min(confidence, Decimal("100")),
            "rule_results": rule_results,
            "explanation": explanation,
            "conditions_met": conditions_met,
        }

    @staticmethod
    def _infer_direction(
        indicator_result: IndicatorResult,
        rule_results: List[Dict[str, Any]],
        explanation_override: Optional[str],
    ) -> str:
        """Infer LONG or SHORT direction from indicator outputs.

        Heuristic:
            * RSI > 50 → bullish bias; RSI < 50 → bearish bias
            * MACD > 0 → bullish; MACD < 0 → bearish
            * ADX high + plus_di > minus_di → bullish; minus_di > plus_di → bearish
            * Price above middle Bollinger Band → bullish; below → bearish
        """
        outputs = indicator_result.values
        bullish_score = 0
        bearish_score = 0

        rsi = outputs.get("rsi", [])
        if rsi and rsi[-1] is not None:
            if rsi[-1] > Decimal("50"):
                bullish_score += 1
            elif rsi[-1] < Decimal("50"):
                bearish_score += 1

        macd = outputs.get("macd", [])
        if macd and macd[-1] is not None:
            if macd[-1] > Decimal("0"):
                bullish_score += 1
            elif macd[-1] < Decimal("0"):
                bearish_score += 1

        pdi = outputs.get("plus_di", [])
        mdi = outputs.get("minus_di", [])
        if pdi and mdi and pdi[-1] is not None and mdi[-1] is not None:
            if pdi[-1] > mdi[-1]:
                bullish_score += 1
            elif mdi[-1] > pdi[-1]:
                bearish_score += 1

        middle = outputs.get("middle", [])
        close_series = outputs.get("close", [])
        if middle and close_series and middle[-1] is not None and close_series[-1] is not None:
            if close_series[-1] > middle[-1]:
                bullish_score += 1
            elif close_series[-1] < middle[-1]:
                bearish_score += 1

        if bullish_score > bearish_score:
            return "LONG"
        elif bearish_score > bullish_score:
            return "SHORT"
        return "NONE"
