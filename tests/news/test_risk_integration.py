"""Tests for Phase 6 ↔ Phase 7 news/risk integration.

Verifies the news gate is backward-compatible (None ⇒ no gate), blocks new
entries on blocking contexts, and flags caution without blocking.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.news.base import Importance, NewsWindowStatus
from src.news.models import NewsRiskContext
from src.risk_management.base import (
    AccountSnapshot,
    RiskDecisionStatus,
    RiskParameters,
)
from src.risk_management.config import RiskConfig, test_policy
from src.risk_management.service import RiskEngine


def _spec():
    from src.market_data.models import InstrumentSpec, InstrumentType, VolumeType
    return InstrumentSpec(
        canonical_symbol="EURUSD", name="EURUSD", instrument_type=InstrumentType.FOREX,
        base_currency="EUR", quote_currency="USD", tick_size=Decimal("0.00001"),
        contract_size=Decimal("100000"), volume_type=VolumeType.TICK,
    )


def _account(leverage=Decimal("30")):
    return AccountSnapshot(
        login=1, name="t", server="t", currency="USD", balance=Decimal("10000"),
        equity=Decimal("10000"), margin=Decimal("0"), free_margin=Decimal("10000"),
        trade_allowed=True, trade_mode="demo", leverage=leverage,
        timestamp=datetime.now(timezone.utc), data_source="mock",
    )


def _relaxed_policy():
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


def _params():
    return RiskParameters(
        signal_id="s1", symbol="EURUSD", instrument_type="forex",
        direction="LONG", reference_price=Decimal("1.1000"),
        technical_invalidation=None, stop_loss_price=Decimal("1.0950"),
        take_profit_price=None, stop_distance=None, atr_value=None,
        atr_multiplier=None, reward_to_risk=Decimal("2.0"),
        swing_high=None, swing_low=None, account_currency="USD",
    )


def _engine():
    eng = RiskEngine(config=RiskConfig(
        policy=_relaxed_policy(), validated=True, validation_errors=[]
    ))
    eng.set_instrument_specs({"EURUSD": _spec()})
    return eng


def _news_context(status, importance=Importance.HIGH, reason=None):
    return NewsRiskContext(
        instrument="EURUSD",
        max_importance=importance,
        window_status=status,
        restriction_reason=reason,
        evaluated_at=datetime.now(timezone.utc),
    )


def test_backward_compatible_none_context_approved():
    eng = _engine()
    decision = eng.evaluate_signal(_params(), _account(), news_context=None)
    assert decision.status == RiskDecisionStatus.APPROVED


def test_clear_context_approved():
    eng = _engine()
    decision = eng.evaluate_signal(
        _params(), _account(),
        news_context=_news_context(NewsWindowStatus.NEWS_CLEAR),
    )
    assert decision.status == RiskDecisionStatus.APPROVED


def test_blocking_context_rejected():
    eng = _engine()
    decision = eng.evaluate_signal(
        _params(), _account(),
        news_context=_news_context(
            NewsWindowStatus.BLOCK_NEW_ENTRIES, reason="High impact CPI in 10m"
        ),
    )
    assert decision.status == RiskDecisionStatus.REJECTED
    assert any("news window" in r.lower() for r in decision.rejection_reasons)


def test_event_time_uncertain_context_rejected():
    eng = _engine()
    decision = eng.evaluate_signal(
        _params(), _account(),
        news_context=_news_context(NewsWindowStatus.EVENT_TIME_UNCERTAIN),
    )
    assert decision.status == RiskDecisionStatus.REJECTED
    assert any("news window" in r.lower() for r in decision.rejection_reasons)


def test_data_unavailable_context_rejected():
    eng = _engine()
    decision = eng.evaluate_signal(
        _params(), _account(),
        news_context=_news_context(NewsWindowStatus.NEWS_DATA_UNAVAILABLE),
    )
    assert decision.status == RiskDecisionStatus.REJECTED


def test_caution_context_approved_with_warning():
    eng = _engine()
    decision = eng.evaluate_signal(
        _params(), _account(),
        news_context=_news_context(
            NewsWindowStatus.NEWS_CAUTION, reason="Approaching medium impact event"
        ),
    )
    assert decision.status == RiskDecisionStatus.APPROVED
    assert any("news" in w.lower() or "approaching" in w.lower()
               for w in decision.warnings)


def test_news_gate_precedes_other_checks():
    # Even a signal that would otherwise be rejected for a bad stop is reported
    # as a news rejection when blocked (gate runs early).
    eng = _engine()
    bad = RiskParameters(
        signal_id="s1", symbol="EURUSD", instrument_type="forex",
        direction="LONG", reference_price=Decimal("1.1000"),
        technical_invalidation=None, stop_loss_price=Decimal("1.1050"),  # wrong side
        take_profit_price=None, stop_distance=None, atr_value=None,
        atr_multiplier=None, reward_to_risk=Decimal("2.0"),
        swing_high=None, swing_low=None, account_currency="USD",
    )
    decision = eng.evaluate_signal(
        bad, _account(),
        news_context=_news_context(NewsWindowStatus.BLOCK_NEW_ENTRIES, reason="NFP"),
    )
    assert decision.status == RiskDecisionStatus.REJECTED
    assert any("news window" in r.lower() for r in decision.rejection_reasons)