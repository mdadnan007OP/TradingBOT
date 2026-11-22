"""Stop-loss and take-profit tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.risk_management.base import RiskParameters
from src.risk_management.config import TakeProfitMethod, test_policy
from src.risk_management.stop_loss import (
    StopLossResult,
    calculate_stop_price,
    derive_stop_distance,
    validate_stop_loss_price,
)
from src.risk_management.take_profit import (
    derive_target_distance,
    validate_take_profit_price,
)


def _params(direction="LONG", entry=Decimal("1.1000"), stop=None, **overrides):
    p = RiskParameters(
        signal_id="s1",
        symbol="EURUSD",
        instrument_type="forex",
        direction=direction,
        reference_price=entry,
        technical_invalidation=None,
        stop_loss_price=stop,
        take_profit_price=None,
        stop_distance=None,
        atr_value=None,
        atr_multiplier=None,
        reward_to_risk=None,
        swing_high=None,
        swing_low=None,
    )
    for k, v in overrides.items():
        object.__setattr__(p, k, v)
    return p


class TestStopLossSide:
    def test_long_stop_below_entry(self):
        r = validate_stop_loss_price(
            Decimal("1.1000"), Decimal("1.0950"), "LONG", test_policy()
        )
        assert r.valid
        assert r.stop_distance == Decimal("0.0050")

    def test_long_stop_above_entry_rejected(self):
        r = validate_stop_loss_price(
            Decimal("1.1000"), Decimal("1.1050"), "LONG", test_policy()
        )
        assert not r.valid
        assert any("below" in x.lower() for x in r.reasons)

    def test_short_stop_above_entry(self):
        r = validate_stop_loss_price(
            Decimal("1.1000"), Decimal("1.1050"), "SHORT", test_policy()
        )
        assert r.valid
        assert r.stop_distance == Decimal("0.0050")

    def test_short_stop_below_entry_rejected(self):
        r = validate_stop_loss_price(
            Decimal("1.1000"), Decimal("1.0950"), "SHORT", test_policy()
        )
        assert not r.valid
        assert any("above" in x.lower() for x in r.reasons)

    def test_zero_distance_rejected(self):
        r = validate_stop_loss_price(
            Decimal("1.1000"), Decimal("1.1000"), "LONG", test_policy()
        )
        assert not r.valid

    def test_min_stop_distance(self):
        policy = test_policy()
        # force min_stop_distance higher than actual
        policy = policy.__class__(
            version=policy.version, enabled=policy.enabled,
            sizing_method=policy.sizing_method,
            risk_per_trade_percent=policy.risk_per_trade_percent,
            fixed_risk_amount=policy.fixed_risk_amount,
            min_reward_to_risk=policy.min_reward_to_risk,
            max_volume=policy.max_volume,
            default_stop_method=policy.default_stop_method,
            atr_multiplier=policy.atr_multiplier,
            min_stop_distance=Decimal("0.0100"),
            max_stop_distance=policy.max_stop_distance,
            max_stop_distance_percent=policy.max_stop_distance_percent,
            default_tp_method=policy.default_tp_method,
            default_reward_to_risk=policy.default_reward_to_risk,
            max_daily_loss_percent=policy.max_daily_loss_percent,
            max_daily_loss_amount=policy.max_daily_loss_amount,
            daily_reset_time=policy.daily_reset_time,
            daily_reset_timezone=policy.daily_reset_timezone,
            max_equity_drawdown_percent=policy.max_equity_drawdown_percent,
            max_balance_drawdown_percent=policy.max_balance_drawdown_percent,
            max_positions=policy.max_positions,
            max_portfolio_risk_percent=policy.max_portfolio_risk_percent,
            max_exposure_per_instrument_percent=policy.max_exposure_per_instrument_percent,
            max_exposure_per_asset_class_percent=policy.max_exposure_per_asset_class_percent,
            max_directional_exposure_percent=policy.max_directional_exposure_percent,
            max_spread_pips=policy.max_spread_pips,
            max_slippage_estimate=policy.max_slippage_estimate,
            max_consecutive_losses=policy.max_consecutive_losses,
            max_margin_usage_percent=policy.max_margin_usage_percent,
            cooldown_minutes=policy.cooldown_minutes,
            cooldown_after_rejection=policy.cooldown_after_rejection,
            instrument_groups=policy.instrument_groups,
            correlation_window=policy.correlation_window,
            min_correlation_data_points=policy.min_correlation_data_points,
            max_correlation_threshold=policy.max_correlation_threshold,
        )
        r = validate_stop_loss_price(
            Decimal("1.1000"), Decimal("1.0995"), "LONG", policy
        )
        assert not r.valid
        assert any("minimum" in x.lower() for x in r.reasons)

    def test_calculate_stop_price_long(self):
        assert calculate_stop_price(Decimal("1.1000"), Decimal("0.0050"), "LONG") == Decimal("1.0950")

    def test_calculate_stop_price_short(self):
        assert calculate_stop_price(Decimal("1.1000"), Decimal("0.0050"), "SHORT") == Decimal("1.1050")


class TestStopDerivation:
    def test_explicit_stop_price(self):
        p = _params("LONG", Decimal("1.1000"), Decimal("1.0950"))
        d = derive_stop_distance(p, test_policy())
        assert d == Decimal("0.0050")

    def test_technical_invalidation(self):
        p = _params("LONG", Decimal("1.1000"), None, technical_invalidation=Decimal("1.0900"))
        p = RiskParameters(
            signal_id=p.signal_id, symbol=p.symbol, instrument_type=p.instrument_type,
            direction=p.direction, reference_price=p.reference_price,
            technical_invalidation=Decimal("1.0900"),
            stop_loss_price=p.stop_loss_price, take_profit_price=p.take_profit_price,
            stop_distance=p.stop_distance, atr_value=p.atr_value,
            atr_multiplier=p.atr_multiplier, reward_to_risk=p.reward_to_risk,
            swing_high=p.swing_high, swing_low=p.swing_low,
            stop_method="technical_invalidation",
        )
        d = derive_stop_distance(p, test_policy())
        assert d == Decimal("0.0100")

    def test_atr_based(self):
        p = _params("LONG", Decimal("1.1000"), None, atr_value=Decimal("0.0020"))
        p = RiskParameters(
            signal_id=p.signal_id, symbol=p.symbol, instrument_type=p.instrument_type,
            direction=p.direction, reference_price=p.reference_price,
            technical_invalidation=p.technical_invalidation,
            stop_loss_price=p.stop_loss_price, take_profit_price=p.take_profit_price,
            stop_distance=p.stop_distance, atr_value=Decimal("0.0020"),
            atr_multiplier=Decimal("2.0"), reward_to_risk=p.reward_to_risk,
            swing_high=p.swing_high, swing_low=p.swing_low,
            stop_method="atr_based",
        )
        d = derive_stop_distance(p, test_policy())
        assert d == Decimal("0.0040")

    def test_missing_stop_returns_none(self):
        p = _params("LONG", Decimal("1.1000"), None)
        assert derive_stop_distance(p, test_policy()) is None


class TestTakeProfitSide:
    def test_long_tp_above_entry(self):
        r = validate_take_profit_price(
            Decimal("1.1000"), Decimal("0.0050"), Decimal("1.1100"), "LONG", test_policy()
        )
        assert r.valid
        assert r.target_distance == Decimal("0.0100")
        assert r.reward_to_risk == Decimal("2.0")

    def test_short_tp_below_entry(self):
        r = validate_take_profit_price(
            Decimal("1.1000"), Decimal("0.0050"), Decimal("1.0900"), "SHORT", test_policy()
        )
        assert r.valid
        assert r.target_distance == Decimal("0.0100")

    def test_rr_below_minimum_rejected(self):
        r = validate_take_profit_price(
            Decimal("1.1000"), Decimal("0.0100"), Decimal("1.1050"), "LONG", test_policy()
        )
        # target 0.0050, stop 0.0100 -> RR 0.5 < 1.5
        assert not r.valid
        assert any("reward-to-risk" in x.lower() for x in r.reasons)

    def test_zero_target_rejected(self):
        r = validate_take_profit_price(
            Decimal("1.1000"), Decimal("0.0050"), Decimal("1.1000"), "LONG", test_policy()
        )
        assert not r.valid

    def test_tp_above_entry_for_short_rejected(self):
        r = validate_take_profit_price(
            Decimal("1.1000"), Decimal("0.0050"), Decimal("1.1100"), "SHORT", test_policy()
        )
        assert not r.valid


class TestTPDerivation:
    def test_reward_to_risk_target(self):
        p = _params("LONG", Decimal("1.1000"), None)
        p = RiskParameters(
            signal_id=p.signal_id, symbol=p.symbol, instrument_type=p.instrument_type,
            direction=p.direction, reference_price=p.reference_price,
            technical_invalidation=p.technical_invalidation,
            stop_loss_price=p.stop_loss_price, take_profit_price=p.take_profit_price,
            stop_distance=p.stop_distance, atr_value=p.atr_value,
            atr_multiplier=p.atr_multiplier, reward_to_risk=Decimal("3.0"),
            swing_high=p.swing_high, swing_low=p.swing_low,
        )
        d = derive_target_distance(p, Decimal("0.0050"), test_policy())
        assert d == Decimal("0.0150")

    def test_atr_based_tp(self):
        p = _params("LONG", Decimal("1.1000"), None, atr_value=Decimal("0.0020"))
        p = RiskParameters(
            signal_id=p.signal_id, symbol=p.symbol, instrument_type=p.instrument_type,
            direction=p.direction, reference_price=p.reference_price,
            technical_invalidation=p.technical_invalidation,
            stop_loss_price=p.stop_loss_price, take_profit_price=p.take_profit_price,
            stop_distance=p.stop_distance, atr_value=Decimal("0.0020"),
            atr_multiplier=Decimal("1.5"), reward_to_risk=p.reward_to_risk,
            swing_high=p.swing_high, swing_low=p.swing_low,
            tp_method=TakeProfitMethod.ATR_BASED,
        )
        d = derive_target_distance(p, Decimal("0.0050"), test_policy())
        assert d == Decimal("0.0030")
