"""Portfolio exposure, correlation, margin, circuit breaker tests."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.risk_management.base import AccountSnapshot, PositionExposure
from src.risk_management.config import test_policy
from src.risk_management.correlation import evaluate_correlation, pearson_correlation
from src.risk_management.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerReason,
    CircuitBreakerResult,
)
from src.risk_management.exposure import (
    ExposureInput,
    aggregate_exposure,
    compute_position_exposure,
)
from src.risk_management.margin import (
    MarginResult,
    estimate_required_margin,
    validate_margin,
)
from src.risk_management.portfolio_risk import (
    PortfolioRiskResult,
    evaluate_portfolio_risk,
)


class TestExposure:
    def test_single_position_exposure(self):
        e = compute_position_exposure(
            "EURUSD", "forex", "LONG", Decimal("0.20"), Decimal("1.1000"),
            Decimal("100000"), Decimal("1"),
        )
        # notional = 0.20 * 1.1000 * 100000 = 22000
        assert e.notional == Decimal("22000.00")
        assert e.volume == Decimal("0.20")

    def test_aggregate_multiple_positions(self):
        from types import SimpleNamespace

        def _d(v):
            return SimpleNamespace(value=v)

        positions = [
            SimpleNamespace(
                symbol="EURUSD", instrument_type="forex",
                direction=_d("LONG"), volume=Decimal("0.20"), open_price=Decimal("1.1000"),
            ),
            SimpleNamespace(
                symbol="XAUUSD", instrument_type="metal",
                direction=_d("SHORT"), volume=Decimal("0.10"), open_price=Decimal("2000.00"),
            ),
        ]
        summary = aggregate_exposure(positions, contract_sizes={"EURUSD": Decimal("100000"), "XAUUSD": Decimal("100")})
        assert summary.total_positions == 2
        assert summary.by_instrument["EURUSD"].notional == Decimal("22000.00")
        assert summary.by_instrument["XAUUSD"].notional == Decimal("20000.00")
        assert summary.directional_bias == "long"


class TestPortfolioRisk:
    def test_within_limits(self):
        summary = __import__("src.risk_management.models", fromlist=["ExposureSummary"]).ExposureSummary(
            total_positions=1, total_notional=Decimal("22000"),
            total_risk=Decimal("100"), long_exposure=Decimal("22000"),
            short_exposure=Decimal("0"),
        )
        res = evaluate_portfolio_risk(
            summary=summary,
            proposed_volume=Decimal("0.01"),
            proposed_notional=Decimal("1000"),
            proposed_direction="LONG",
            proposed_symbol="GBPUSD",
            proposed_asset_class="forex",
            equity=Decimal("10000.00"),
            policy=test_policy(),
        )
        assert res.within_limits
        assert res.max_positions_ok

    def test_max_positions_reached(self):
        from src.risk_management.models import ExposureSummary
        summary = ExposureSummary(
            total_positions=5, total_notional=Decimal("0"),
            total_risk=Decimal("0"), long_exposure=Decimal("0"),
            short_exposure=Decimal("0"),
        )
        res = evaluate_portfolio_risk(
            summary=summary, proposed_volume=Decimal("0.10"),
            proposed_notional=Decimal("1000"), proposed_direction="LONG",
            proposed_symbol="EURUSD", proposed_asset_class="forex",
            equity=Decimal("10000.00"), policy=test_policy(),
        )
        assert not res.max_positions_ok
        assert not res.within_limits

    def test_instrument_exposure_breach(self):
        from src.risk_management.models import ExposureSummary
        summary = ExposureSummary(
            total_positions=1, total_notional=Decimal("0"),
            total_risk=Decimal("0"), long_exposure=Decimal("0"),
            short_exposure=Decimal("0"),
            by_instrument={
                "EURUSD": PositionExposure(
                    symbol="EURUSD", instrument_type="forex", direction="LONG",
                    volume=Decimal("1.00"), open_price=Decimal("1.1000"),
                    notional=Decimal("18000.00"), asset_class="forex",
                )
            },
        )
        res = evaluate_portfolio_risk(
            summary=summary, proposed_volume=Decimal("0.10"),
            proposed_notional=Decimal("5000"), proposed_direction="LONG",
            proposed_symbol="EURUSD", proposed_asset_class="forex",
            equity=Decimal("10000.00"), policy=test_policy(),
        )
        # 20% of 10000 = 2000 limit; 18000+5000 = 23000 > 2000
        assert not res.instrument_exposure_ok
        assert not res.within_limits


class TestCorrelation:
    def test_pearson_perfect(self):
        x = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")]
        y = [Decimal("2"), Decimal("4"), Decimal("6"), Decimal("8"), Decimal("10")]
        c = pearson_correlation(x, y)
        assert abs(c - Decimal("1")) < Decimal("0.0001")

    def test_pearson_negative(self):
        x = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")]
        y = [Decimal("5"), Decimal("4"), Decimal("3"), Decimal("2"), Decimal("1")]
        c = pearson_correlation(x, y)
        assert abs(c - Decimal("-1")) < Decimal("0.0001")

    def test_pearson_insufficient(self):
        assert pearson_correlation([Decimal("1")], [Decimal("1")]) is None

    def test_correlation_breach(self):
        policy = test_policy()
        returns = {
            "EURUSD": [Decimal(str(i * 0.01)) for i in range(1, 41)],
            "GBPUSD": [Decimal(str(i * 0.02)) for i in range(1, 41)],
        }
        res = evaluate_correlation("GBPUSD", ["EURUSD"], returns, policy)
        assert res.sufficient_data
        assert res.breach  # perfectly correlated
        assert "EURUSD" in res.correlated_symbols
        assert res.max_correlation is not None
        assert abs(res.max_correlation - Decimal("1")) < Decimal("0.0001")

    def test_correlation_insufficient_data(self):
        policy = test_policy()
        returns = {"EURUSD": [Decimal("0.01")] * 5}
        res = evaluate_correlation("GBPUSD", ["EURUSD"], returns, policy)
        assert not res.sufficient_data
        assert not res.breach


class TestMargin:
    def test_estimate_required_margin(self):
        m = estimate_required_margin(
            Decimal("0.20"), Decimal("1.1000"), Decimal("100000"), Decimal("30")
        )
        # notional = 22000; /30 = 733.33
        assert m == Decimal("22000.00") / Decimal("30")

    def test_margin_sufficient(self):
        r = validate_margin(
            volume=Decimal("0.20"), price=Decimal("1.1000"),
            contract_size=Decimal("100000"),
            account_equity=Decimal("10000.00"),
            account_free_margin=Decimal("10000.00"),
            account_margin_used=Decimal("0"),
            leverage=Decimal("30"),
        )
        assert r.sufficient
        assert r.snapshot.required_margin == Decimal("22000.00") / Decimal("30")

    def test_margin_insufficient(self):
        r = validate_margin(
            volume=Decimal("10.00"), price=Decimal("1.1000"),
            contract_size=Decimal("100000"),
            account_equity=Decimal("10000.00"),
            account_free_margin=Decimal("100.00"),
            account_margin_used=Decimal("0"),
            leverage=Decimal("30"),
        )
        assert not r.sufficient
        assert r.reasons


class TestCircuitBreaker:
    def test_trip_and_lock(self):
        cb = CircuitBreaker()
        res = cb.evaluate(
            CircuitBreakerReason.DAILY_LOSS_LIMIT,
            datetime.now(timezone.utc),
        )
        assert res.locked
        assert cb.is_locked()

    def test_reset_requires_authorization(self):
        cb = CircuitBreaker()
        cb.evaluate(CircuitBreakerReason.DAILY_LOSS_LIMIT, datetime.now(timezone.utc))
        res = cb.reset(authorized=False)
        assert res.locked
        res = cb.reset(authorized=True)
        assert not res.locked
        assert not cb.is_locked()

    def test_consecutive_loss_threshold(self):
        cb = CircuitBreaker()
        res = cb.record_consecutive_loss(4, 5)
        assert not res.locked
        res = cb.record_consecutive_loss(5, 5)
        assert res.locked
