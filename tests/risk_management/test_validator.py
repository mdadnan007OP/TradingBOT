"""Risk policy validation tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.risk_management.config import (
    RiskPolicy,
    SizingMethod,
    StopMethod,
    TakeProfitMethod,
    test_policy,
)
from src.risk_management.validator import validate_policy


class TestPolicyValidation:
    def test_valid_policy(self):
        errs = validate_policy(test_policy())
        assert errs == []

    def test_invalid_risk_percent(self):
        p = test_policy()
        p = p.__class__(
            version=p.version, enabled=p.enabled, sizing_method=p.sizing_method,
            risk_per_trade_percent=Decimal("0"),
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
            max_exposure_per_instrument_percent=p.max_exposure_per_instrument_percent,
            max_exposure_per_asset_class_percent=p.max_exposure_per_asset_class_percent,
            max_directional_exposure_percent=p.max_directional_exposure_percent,
            max_spread_pips=p.max_spread_pips,
            max_slippage_estimate=p.max_slippage_estimate,
            max_consecutive_losses=p.max_consecutive_losses,
            max_margin_usage_percent=p.max_margin_usage_percent,
            cooldown_minutes=p.cooldown_minutes,
            cooldown_after_rejection=p.cooldown_after_rejection,
            instrument_groups=p.instrument_groups,
            correlation_window=p.correlation_window,
            min_correlation_data_points=p.min_correlation_data_points,
            max_correlation_threshold=p.max_correlation_threshold,
        )
        errs = validate_policy(p)
        assert any("risk_per_trade_percent" in e for e in errs)

    def test_disabled_policy(self):
        p = test_policy()
        p = p.__class__(
            version=p.version, enabled=False, sizing_method=p.sizing_method,
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
            max_exposure_per_instrument_percent=p.max_exposure_per_instrument_percent,
            max_exposure_per_asset_class_percent=p.max_exposure_per_asset_class_percent,
            max_directional_exposure_percent=p.max_directional_exposure_percent,
            max_spread_pips=p.max_spread_pips,
            max_slippage_estimate=p.max_slippage_estimate,
            max_consecutive_losses=p.max_consecutive_losses,
            max_margin_usage_percent=p.max_margin_usage_percent,
            cooldown_minutes=p.cooldown_minutes,
            cooldown_after_rejection=p.cooldown_after_rejection,
            instrument_groups=p.instrument_groups,
            correlation_window=p.correlation_window,
            min_correlation_data_points=p.min_correlation_data_points,
            max_correlation_threshold=p.max_correlation_threshold,
        )
        errs = validate_policy(p)
        assert any("disabled" in e.lower() for e in errs)

    def test_fixed_monetary_missing_amount(self):
        p = test_policy()
        p = p.__class__(
            version=p.version, enabled=p.enabled,
            sizing_method=SizingMethod.FIXED_MONETARY,
            risk_per_trade_percent=p.risk_per_trade_percent,
            fixed_risk_amount=None,
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
            max_exposure_per_instrument_percent=p.max_exposure_per_instrument_percent,
            max_exposure_per_asset_class_percent=p.max_exposure_per_asset_class_percent,
            max_directional_exposure_percent=p.max_directional_exposure_percent,
            max_spread_pips=p.max_spread_pips,
            max_slippage_estimate=p.max_slippage_estimate,
            max_consecutive_losses=p.max_consecutive_losses,
            max_margin_usage_percent=p.max_margin_usage_percent,
            cooldown_minutes=p.cooldown_minutes,
            cooldown_after_rejection=p.cooldown_after_rejection,
            instrument_groups=p.instrument_groups,
            correlation_window=p.correlation_window,
            min_correlation_data_points=p.min_correlation_data_points,
            max_correlation_threshold=p.max_correlation_threshold,
        )
        errs = validate_policy(p)
        assert any("fixed_risk_amount" in e for e in errs)

    def test_test_policy_is_valid(self):
        assert test_policy().is_valid()
