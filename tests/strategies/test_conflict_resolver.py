"""Tests for the Signal Conflict Resolver."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.strategies.base import (
    MarketRegime,
    Signal,
    SignalDirection,
    SignalStatus,
    StrategyResult,
)
from src.strategies.conflict_resolver import SignalConflictResolver
from src.market_data.models import MarketTimeframe


def _make_signal(direction: SignalDirection, strategy: str = "S1") -> Signal:
    return Signal(
        signal_id=f"{strategy}-1",
        strategy_name=strategy,
        strategy_version="1.0.0",
        symbol="EURUSD",
        instrument_type="forex",
        direction=direction,
        status=SignalStatus.ACTIVE,
        entry_timeframe=MarketTimeframe.H1,
        confirmation_timeframes=[],
        signal_timestamp=__import__("datetime").datetime(
            2024, 1, 1, 12, tzinfo=__import__("datetime").timezone.utc
        ),
        market_data_timestamp=__import__("datetime").datetime(
            2024, 1, 1, 11, tzinfo=__import__("datetime").timezone.utc
        ),
        reference_price=Decimal("100"),
        technical_invalidation=None,
        parameters=__import__(
            "src.indicators.base", fromlist=["IndicatorParameters"]
        ).IndicatorParameters(),
        indicator_snapshot={},
        market_regime=MarketRegime.TRENDING,
        confirmation_conditions=[],
        explanation="test",
        expiry_conditions=[],
        data_source=__import__(
            "src.market_data.models", fromlist=["DataSource"]
        ).DataSource.SIMULATED,
        strategy_validity_state="valid",
    )


def _make_result(strategy_name: str, direction: SignalDirection) -> StrategyResult:
    sig = _make_signal(direction, strategy_name)
    return StrategyResult(
        strategy_name=strategy_name,
        symbol="EURUSD",
        timeframe=MarketTimeframe.H1,
        signals=[sig],
        rejections=[],
        market_regime=MarketRegime.TRENDING,
        indicator_snapshots={},
    )


class TestSignalConflictResolver:
    def setup_method(self):
        self.resolver = SignalConflictResolver()

    def test_no_conflicts_all_long(self):
        results = [
            _make_result("Strat1", SignalDirection.LONG),
            _make_result("Strat2", SignalDirection.LONG),
        ]
        detection = self.resolver.detect(results)
        assert detection["has_conflicts"] is False
        assert detection["aggregated_direction"] == "LONG"

    def test_no_conflicts_all_short(self):
        results = [
            _make_result("Strat1", SignalDirection.SHORT),
            _make_result("Strat2", SignalDirection.SHORT),
        ]
        detection = self.resolver.detect(results)
        assert detection["has_conflicts"] is False
        assert detection["aggregated_direction"] == "SHORT"

    def test_conflict_long_vs_short(self):
        results = [
            _make_result("TrendFollowing", SignalDirection.LONG),
            _make_result("LiquidityHunting", SignalDirection.SHORT),
        ]
        detection = self.resolver.detect(results)
        assert detection["has_conflicts"] is True
        assert detection["aggregated_direction"] is None
        assert len(detection["conflicts"]) == 1
        assert detection["conflicts"][0]["symbol"] == "EURUSD"

    def test_agreement_groups(self):
        results = [
            _make_result("A", SignalDirection.LONG),
            _make_result("B", SignalDirection.LONG),
            _make_result("C", SignalDirection.SHORT),
        ]
        detection = self.resolver.detect(results)
        assert detection["has_conflicts"] is True
        groups = detection["agreement_groups"]
        # Should have LONG group and SHORT group
        long_group = [g for g in groups if "A" in g and "B" in g]
        short_group = [g for g in groups if "C" in g]
        assert len(long_group) == 1
        assert len(short_group) == 1

    def test_aggregate_report_conflicts(self):
        results = [
            _make_result("A", SignalDirection.LONG),
            _make_result("B", SignalDirection.SHORT),
        ]
        agg = self.resolver.aggregate(results, policy="report_conflicts")
        assert agg["policy"] == "report_conflicts"
        assert agg["decision"] == "REPORT_CONFLICTS"
        assert agg["has_conflicts"] is True

    def test_aggregate_unanimous_long(self):
        results = [
            _make_result("A", SignalDirection.LONG),
            _make_result("B", SignalDirection.LONG),
        ]
        agg = self.resolver.aggregate(results, policy="unanimous")
        assert agg["decision"] == "SIGNAL"
        assert agg["direction"] == "LONG"

    def test_aggregate_unanimous_conflict(self):
        results = [
            _make_result("A", SignalDirection.LONG),
            _make_result("B", SignalDirection.SHORT),
        ]
        agg = self.resolver.aggregate(results, policy="unanimous")
        assert agg["decision"] == "NO_CONSENSUS"

    def test_aggregate_majority_long(self):
        results = [
            _make_result("A", SignalDirection.LONG),
            _make_result("B", SignalDirection.LONG),
            _make_result("C", SignalDirection.SHORT),
        ]
        agg = self.resolver.aggregate(results, policy="majority")
        assert agg["decision"] == "SIGNAL"
        assert agg["direction"] == "LONG"

    def test_aggregate_majority_tie(self):
        results = [
            _make_result("A", SignalDirection.LONG),
            _make_result("B", SignalDirection.SHORT),
        ]
        agg = self.resolver.aggregate(results, policy="majority")
        assert agg["decision"] == "NO_SIGNAL"

    def test_aggregate_consensus_conflict(self):
        results = [
            _make_result("A", SignalDirection.LONG),
            _make_result("B", SignalDirection.SHORT),
        ]
        agg = self.resolver.aggregate(results, policy="consensus")
        assert agg["decision"] == "NO_CONSENSUS"
