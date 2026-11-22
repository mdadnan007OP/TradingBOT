"""End-to-end risk engine integration tests."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.market_data.models import InstrumentSpec, InstrumentType, VolumeType
from src.risk_management.base import (
    AccountSnapshot,
    RiskDecisionStatus,
    RiskParameters,
)
from src.risk_management.circuit_breaker import CircuitBreaker, CircuitBreakerReason
from src.risk_management.config import RiskConfig, SizingMethod, StopMethod, TakeProfitMethod, test_policy
from src.risk_management.drawdown import DrawdownTracker
from src.risk_management.models import DailyPnLState
from src.risk_management.service import RiskEngine


def _spec(symbol, contract_size, instrument_type="forex", quote_currency="USD"):
    return InstrumentSpec(
        canonical_symbol=symbol, name=symbol, instrument_type=InstrumentType[instrument_type.upper()],
        base_currency="XXX", quote_currency=quote_currency, tick_size=Decimal("0.01"),
        contract_size=contract_size, volume_type=VolumeType.TICK,
    )


def _account(currency="USD", equity=Decimal("10000.00"), balance=Decimal("10000.00"), leverage=None):
    return AccountSnapshot(
        login=1, name="t", server="t", currency=currency, balance=balance,
        equity=equity, margin=Decimal("0"), free_margin=equity,
        trade_allowed=True, trade_mode="demo", leverage=leverage,
        timestamp=datetime.now(timezone.utc), data_source="mock",
    )


def _relaxed_policy():
    """Policy with generous exposure/margin limits for happy-path engine tests."""
    p = test_policy()
    return p.__class__(
        version=p.version, enabled=p.enabled, sizing_method=p.sizing_method,
        risk_per_trade_percent=p.risk_per_trade_percent,
        fixed_risk_amount=p.fixed_risk_amount,
        min_reward_to_risk=p.min_reward_to_risk, max_volume=p.max_volume,
        default_stop_method=p.default_stop_method, atr_multiplier=p.atr_multiplier,
        min_stop_distance=p.min_stop_distance, max_stop_distance=p.max_stop_distance,
        max_stop_distance_percent=p.max_stop_distance_percent,
        default_tp_method=p.default_tp_method,
        default_reward_to_risk=p.default_reward_to_risk,
        max_daily_loss_percent=p.max_daily_loss_percent,
        max_daily_loss_amount=p.max_daily_loss_amount,
        daily_reset_time=p.daily_reset_time,
        daily_reset_timezone=p.daily_reset_timezone,
        max_equity_drawdown_percent=p.max_equity_drawdown_percent,
        max_balance_drawdown_percent=p.max_balance_drawdown_percent,
        max_positions=p.max_positions,
        max_portfolio_risk_percent=p.max_portfolio_risk_percent,
        max_exposure_per_instrument_percent=Decimal("10.0"),
        max_exposure_per_asset_class_percent=Decimal("10.0"),
        max_directional_exposure_percent=p.max_directional_exposure_percent,
        max_spread_pips=p.max_spread_pips,
        max_slippage_estimate=p.max_slippage_estimate,
        max_consecutive_losses=p.max_consecutive_losses,
        max_margin_usage_percent=Decimal("0.90"),
        cooldown_minutes=p.cooldown_minutes,
        cooldown_after_rejection=p.cooldown_after_rejection,
        instrument_groups=p.instrument_groups,
        correlation_window=p.correlation_window,
        min_correlation_data_points=p.min_correlation_data_points,
        max_correlation_threshold=p.max_correlation_threshold,
    )


def _engine(specs=None, positions=None, policy=None):
    eng = RiskEngine(config=RiskConfig(
        policy=policy or test_policy(), validated=True, validation_errors=[]
    ))
    if specs:
        eng.set_instrument_specs({s.canonical_symbol: s for s in specs})
    if positions:
        eng.set_positions(positions)
    return eng


def _params(direction="LONG", entry=Decimal("1.1000"), stop=Decimal("1.0950"), tp=None,
            symbol="EURUSD", account_currency="USD"):
    return RiskParameters(
        signal_id="s1", symbol=symbol, instrument_type="forex",
        direction=direction, reference_price=entry,
        technical_invalidation=None, stop_loss_price=stop,
        take_profit_price=tp, stop_distance=None, atr_value=None,
        atr_multiplier=None, reward_to_risk=Decimal("2.0"),
        swing_high=None, swing_low=None,
        account_currency=account_currency,
    )


class TestEngineApproved:
    def test_eurusd_long_approved(self):
        eng = _engine(specs=[_spec("EURUSD", Decimal("100000"))], policy=_relaxed_policy())
        decision = eng.evaluate_signal(_params(), _account(leverage=Decimal("30")))
        assert decision.status == RiskDecisionStatus.APPROVED
        assert decision.volume == Decimal("0.20")
        assert decision.monetary_risk == Decimal("100.00")
        assert decision.stop_loss_price == Decimal("1.0950")
        assert decision.take_profit_price == Decimal("1.1100")
        assert decision.reward_to_risk == Decimal("2.0")
        assert decision.rejection_reasons == []

    def test_eurusd_short_approved(self):
        eng = _engine(specs=[_spec("EURUSD", Decimal("100000"))], policy=_relaxed_policy())
        decision = eng.evaluate_signal(
            _params("SHORT", Decimal("1.1000"), Decimal("1.1050"), Decimal("1.0900")),
            _account(leverage=Decimal("30")),
        )
        assert decision.status == RiskDecisionStatus.APPROVED
        assert decision.volume == Decimal("0.20")
        assert decision.stop_loss_price == Decimal("1.1050")
        assert decision.take_profit_price == Decimal("1.0900")
        assert decision.reward_to_risk == Decimal("2.0")
        assert decision.rejection_reasons == []


class TestEngineRejections:
    def test_missing_spec_requires_information(self):
        eng = _engine()  # no specs
        decision = eng.evaluate_signal(_params(), _account())
        assert decision.status == RiskDecisionStatus.REQUIRES_INFORMATION
        assert decision.rejection_reasons

    def test_invalid_stop_rejected(self):
        eng = _engine(specs=[_spec("EURUSD", Decimal("100000"))])
        # LONG stop above entry
        decision = eng.evaluate_signal(
            _params("LONG", Decimal("1.1000"), Decimal("1.1050")),
            _account(),
        )
        assert decision.status == RiskDecisionStatus.REJECTED
        assert decision.rejection_reasons

    def test_below_min_lot_rejected(self):
        eng = _engine(specs=[_spec("EURUSD", Decimal("100000"))], policy=_relaxed_policy())
        # Large stop distance -> risk_per_lot high -> raw volume rounds to 0 -> below min_lot
        decision = eng.evaluate_signal(
            _params("LONG", Decimal("1.1000"), Decimal("0.9999")),
            _account(leverage=Decimal("30")),
        )
        assert decision.status == RiskDecisionStatus.REJECTED
        assert decision.volume is None
        assert any("minimum" in r.lower() for r in decision.rejection_reasons)

    def test_circuit_breaker_locked(self):
        eng = _engine(specs=[_spec("EURUSD", Decimal("100000"))])
        eng.circuit_breaker.evaluate(
            CircuitBreakerReason.DAILY_LOSS_LIMIT,
            datetime.now(timezone.utc),
        )
        decision = eng.evaluate_signal(_params(), _account())
        assert decision.status == RiskDecisionStatus.LOCKED

    def test_drawdown_breach_rejected(self):
        eng = _engine(specs=[_spec("EURUSD", Decimal("100000"))])
        eng.drawdown_tracker = DrawdownTracker(
            Decimal("0.10"), Decimal("0.15")
        )
        # prime high watermark then drop equity below limit
        eng.drawdown_tracker.update(Decimal("10000.00"), Decimal("10000.00"))
        acct = _account(equity=Decimal("8500.00"), balance=Decimal("8500.00"))
        decision = eng.evaluate_signal(_params(), acct)
        assert decision.status == RiskDecisionStatus.REJECTED
        assert any("drawdown" in r.lower() for r in decision.rejection_reasons)

    def test_daily_loss_breach_rejected(self):
        eng = _engine(specs=[_spec("EURUSD", Decimal("100000"))])
        eng.daily_pnl_state = DailyPnLState(
            starting_balance=Decimal("10000"), starting_equity=Decimal("10000"),
            realized_pnl=Decimal("-600"),  # 6% > 5% limit
        )
        decision = eng.evaluate_signal(_params(), _account())
        assert decision.status == RiskDecisionStatus.REJECTED
        assert any("daily loss" in r.lower() for r in decision.rejection_reasons)


class TestEngineDecisionFields:
    def test_decision_has_required_fields(self):
        eng = _engine(specs=[_spec("EURUSD", Decimal("100000"))])
        decision = eng.evaluate_signal(_params(), _account())
        assert decision.signal_id == "s1"
        assert decision.symbol == "EURUSD"
        assert decision.direction == "LONG"
        assert decision.calculation_timestamp is not None
        assert decision.data_source == "mock"
        assert decision.policy_version is not None

    def test_report_building(self):
        from src.risk_management.risk_report import report_to_dict
        eng = _engine(specs=[_spec("EURUSD", Decimal("100000"))], policy=_relaxed_policy())
        decision = eng.evaluate_signal(_params(), _account(leverage=Decimal("30")))
        report = eng.build_report(decision)
        d = report_to_dict(report)
        assert d["decision"]["status"] == "RISK_APPROVED"
        assert d["account"]["currency"] == "USD"
        assert d["policy_version"] is not None
