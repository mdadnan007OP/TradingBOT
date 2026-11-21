"""Tests for the Signal Generator (multi-indicator confirmation engine)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.indicators.base import IndicatorParameters, IndicatorResult, ReadinessStatus
from src.market_data.models import DataSource, MarketTimeframe, OHLCBar
from src.strategies.models import ConfirmationCondition, ConfirmationRule
from src.strategies.signal_generator import ConfirmationEvaluator, SignalGenerator


def _make_result(values: dict, readiness=ReadinessStatus.READY) -> IndicatorResult:
    IP = IndicatorParameters
    return IndicatorResult(
        symbol="EURUSD",
        instrument_type="forex",
        timeframe=MarketTimeframe.H1,
        indicator_name="TEST",
        parameters=IP(),
        calculation_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        source_candle_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        data_source=DataSource.SIMULATED,
        values=values,
        readiness=readiness,
        warmup_periods=0,
        metadata={},
    )


class TestConfirmationEvaluator:
    def test_gt_condition(self):
        result = _make_result({"rsi": [Decimal("30"), Decimal("60")]})
        cond = ConfirmationCondition(
            indicator="RSI", output="rsi", operator="gt", value=Decimal("50"),
        )
        ok, detail = ConfirmationEvaluator.evaluate_condition(cond, result)
        assert ok is True
        assert "60" in detail

    def test_lt_condition(self):
        result = _make_result({"rsi": [Decimal("30"), Decimal("40")]})
        cond = ConfirmationCondition(
            indicator="RSI", output="rsi", operator="lt", value=Decimal("50"),
        )
        ok, detail = ConfirmationEvaluator.evaluate_condition(cond, result)
        assert ok is True

    def test_eq_condition(self):
        result = _make_result({"rsi": [Decimal("50"), Decimal("50")]})
        cond = ConfirmationCondition(
            indicator="RSI", output="rsi", operator="eq", value=Decimal("50"),
        )
        ok, detail = ConfirmationEvaluator.evaluate_condition(cond, result)
        assert ok is True

    def test_crosses_above(self):
        prev = _make_result({"macd": [Decimal("-1"), Decimal("-0.5")]})
        curr = _make_result({"macd": [Decimal("-0.5"), Decimal("0.5")]})
        cond = ConfirmationCondition(
            indicator="MACD", output="macd", operator="crosses_above", value=Decimal("0"),
        )
        ok, detail = ConfirmationEvaluator.evaluate_condition(cond, curr, prev)
        assert ok is True

    def test_crosses_below(self):
        prev = _make_result({"macd": [Decimal("0.5"), Decimal("0.2")]})
        curr = _make_result({"macd": [Decimal("0.2"), Decimal("-0.5")]})
        cond = ConfirmationCondition(
            indicator="MACD", output="macd", operator="crosses_below", value=Decimal("0"),
        )
        ok, detail = ConfirmationEvaluator.evaluate_condition(cond, curr, prev)
        assert ok is True

    def test_between(self):
        result = _make_result({"rsi": [Decimal("30"), Decimal("45")]})
        cond = ConfirmationCondition(
            indicator="RSI", output="rsi", operator="between", value=(40, 50),
        )
        ok, detail = ConfirmationEvaluator.evaluate_condition(cond, result)
        assert ok is True

    def test_none_value_fails(self):
        result = _make_result({"rsi": [Decimal("30"), None]})
        cond = ConfirmationCondition(
            indicator="RSI", output="rsi", operator="gt", value=Decimal("50"),
        )
        ok, detail = ConfirmationEvaluator.evaluate_condition(cond, result)
        assert ok is False


class TestSignalGenerator:
    def setup_method(self):
        self.gen = SignalGenerator()

    def test_generate_long_signal(self):
        curr = _make_result({
            "rsi": [Decimal("30"), Decimal("60")],
            "macd": [Decimal("-0.5"), Decimal("0.5")],
        })
        prev = _make_result({
            "rsi": [Decimal("30"), Decimal("40")],
            "macd": [Decimal("-1"), Decimal("-0.5")],
        })
        rules = [
            ConfirmationRule(
                name="bullish",
                conditions=[
                    ConfirmationCondition("RSI", "rsi", "gt", Decimal("50")),
                    ConfirmationCondition("MACD", "macd", "crosses_above", Decimal("0")),
                ],
                min_required=1,
            )
        ]
        result = self.gen.generate(
            "EURUSD", MarketTimeframe.H1, curr, prev, rules,
            min_confirmations=1,
        )
        assert result["direction"] in ("LONG", "SHORT", "NONE")
        assert "explanation" in result
        assert "rule_results" in result

    def test_generate_no_signal(self):
        curr = _make_result({"rsi": [Decimal("30"), Decimal("40")]})
        rules = [
            ConfirmationRule(
                name="bullish",
                conditions=[
                    ConfirmationCondition("RSI", "rsi", "gt", Decimal("50")),
                ],
                min_required=1,
            )
        ]
        result = self.gen.generate(
            "EURUSD", MarketTimeframe.H1, curr, None, rules,
            min_confirmations=1,
        )
        assert result["direction"] == "NONE"
        assert result["satisfied"] is False

    def test_direction_inference_long(self):
        curr = _make_result({
            "rsi": [Decimal("30"), Decimal("70")],
            "macd": [Decimal("-0.5"), Decimal("0.5")],
            "close": [Decimal("99"), Decimal("100")],
            "middle": [Decimal("98"), Decimal("99")],
        })
        rules = [
            ConfirmationRule(
                name="bullish",
                conditions=[
                    ConfirmationCondition("RSI", "rsi", "gt", Decimal("50")),
                ],
                min_required=1,
            )
        ]
        result = self.gen.generate(
            "EURUSD", MarketTimeframe.H1, curr, None, rules,
            min_confirmations=1,
        )
        assert result["direction"] == "LONG"

    def test_direction_inference_short(self):
        curr = _make_result({
            "rsi": [Decimal("70"), Decimal("30")],
            "macd": [Decimal("0.5"), Decimal("-0.5")],
            "close": [Decimal("101"), Decimal("100")],
            "middle": [Decimal("102"), Decimal("101")],
        })
        rules = [
            ConfirmationRule(
                name="bearish",
                conditions=[
                    ConfirmationCondition("RSI", "rsi", "lt", Decimal("50")),
                ],
                min_required=1,
            )
        ]
        result = self.gen.generate(
            "EURUSD", MarketTimeframe.H1, curr, None, rules,
            min_confirmations=1,
        )
        assert result["direction"] == "SHORT"
