"""Position sizing tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.market_data.models import InstrumentSpec, InstrumentType, VolumeType
from src.risk_management.base import AccountSnapshot, RiskParameters
from src.risk_management.config import test_policy
from src.risk_management.position_sizing import (
    PositionSizer,
    quote_to_account_rate,
    risk_amount_from_policy,
    round_down_to_step,
)


def _spec(
    symbol,
    instrument_type,
    contract_size,
    lot_step=Decimal("0.01"),
    min_lot=Decimal("0.01"),
    max_lot=Decimal("100.0"),
    quote_currency="USD",
):
    return InstrumentSpec(
        canonical_symbol=symbol,
        name=symbol,
        instrument_type=instrument_type,
        base_currency="XXX",
        quote_currency=quote_currency,
        tick_size=Decimal("0.01"),
        contract_size=contract_size,
        volume_type=VolumeType.TICK,
    )


def _params(direction="LONG", entry=Decimal("1.1000"), stop=Decimal("1.0950"), rates=None, symbol="EURUSD", account_currency="USD"):
    return RiskParameters(
        signal_id="s1",
        symbol=symbol,
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
        account_currency=account_currency,
        rates=rates or {},
    )


def _account(currency="USD", equity=Decimal("10000.00"), balance=Decimal("10000.00")):
    return AccountSnapshot(
        login=1,
        name="t",
        server="t",
        currency=currency,
        balance=balance,
        equity=equity,
        margin=Decimal("0"),
        free_margin=equity,
        trade_allowed=True,
        trade_mode="demo",
    )


LOT_KW = dict(lot_step=Decimal("0.01"), min_lot=Decimal("0.01"), max_lot=Decimal("100.0"))


class TestRounding:
    def test_round_down_to_step(self):
        assert round_down_to_step(Decimal("0.237"), Decimal("0.01")) == Decimal("0.23")
        assert round_down_to_step(Decimal("0.239"), Decimal("0.01")) == Decimal("0.23")
        assert round_down_to_step(Decimal("0.20"), Decimal("0.01")) == Decimal("0.20")

    def test_never_round_up(self):
        assert round_down_to_step(Decimal("0.237"), Decimal("0.01")) < Decimal("0.24")


class TestForexSizing:
    def _sizer(self, spec):
        return PositionSizer(spec, "USD", **LOT_KW)

    def test_eurusd_long_exact(self):
        spec = _spec("EURUSD", InstrumentType.FOREX, Decimal("100000"))
        sizer = self._sizer(spec)
        p = _params("LONG", Decimal("1.1000"), Decimal("1.0950"))
        res = sizer.size(p, test_policy(), Decimal("10000.00"), Decimal("10000.00"))
        assert res.volume == Decimal("0.20")
        assert res.monetary_risk == Decimal("100.00")
        assert res.risk_percent == Decimal("1.00")
        assert res.stop_distance == Decimal("0.0050")
        assert res.reasons == []

    def test_eurusd_short_exact(self):
        spec = _spec("EURUSD", InstrumentType.FOREX, Decimal("100000"))
        sizer = self._sizer(spec)
        p = _params("SHORT", Decimal("1.1000"), Decimal("1.1050"))
        res = sizer.size(p, test_policy(), Decimal("10000.00"), Decimal("10000.00"))
        assert res.volume == Decimal("0.20")
        assert res.monetary_risk == Decimal("100.00")
        assert res.stop_distance == Decimal("0.0050")

    def test_volume_never_exceeds_budget(self):
        spec = _spec("EURUSD", InstrumentType.FOREX, Decimal("100000"))
        sizer = self._sizer(spec)
        p = _params("LONG", Decimal("1.1000"), Decimal("1.0953"))
        res = sizer.size(p, test_policy(), Decimal("10000.00"), Decimal("10000.00"))
        assert res.monetary_risk <= Decimal("100.00")

    def test_below_min_lot_rejected(self):
        spec = _spec("EURUSD", InstrumentType.FOREX, Decimal("100000"))
        sizer = PositionSizer(spec, "USD", **LOT_KW)
        # Large stop distance -> risk_per_lot high -> raw volume rounds to 0 -> below min_lot
        p = _params("LONG", Decimal("1.1000"), Decimal("0.9999"), symbol="EURUSD")
        res = sizer.size(p, test_policy(), Decimal("10000.00"), Decimal("10000.00"))
        assert res.volume is None
        assert any("minimum" in r for r in res.reasons)


class TestMetalsSizing:
    def test_xauusd_long_exact(self):
        spec = _spec("XAUUSD", InstrumentType.METAL, Decimal("100"))
        sizer = PositionSizer(spec, "USD", **LOT_KW)
        p = _params("LONG", Decimal("2000.00"), Decimal("1997.00"), symbol="XAUUSD")
        res = sizer.size(p, test_policy(), Decimal("10000.00"), Decimal("10000.00"))
        # risk_per_lot = 3.00 * 100 = $300; volume = 100/300 = 0.3333 -> 0.33
        assert res.volume == Decimal("0.33")
        assert res.monetary_risk == Decimal("99.00")

    def test_xauusd_short(self):
        spec = _spec("XAUUSD", InstrumentType.METAL, Decimal("100"))
        sizer = PositionSizer(spec, "USD", **LOT_KW)
        p = _params("SHORT", Decimal("2000.00"), Decimal("2003.00"), symbol="XAUUSD")
        res = sizer.size(p, test_policy(), Decimal("10000.00"), Decimal("10000.00"))
        assert res.volume == Decimal("0.33")
        assert res.monetary_risk == Decimal("99.00")


class TestIndexAndEnergy:
    def test_nas100_long(self):
        spec = _spec("NAS100", InstrumentType.INDEX, Decimal("20"))
        sizer = PositionSizer(spec, "USD", **LOT_KW)
        p = _params("LONG", Decimal("18000.00"), Decimal("17997.00"), symbol="NAS100")
        res = sizer.size(p, test_policy(), Decimal("10000.00"), Decimal("10000.00"))
        # risk_per_lot = 3.00 * 20 = $60; volume = 100/60 = 1.6666 -> 1.66
        assert res.volume == Decimal("1.66")
        assert res.monetary_risk == Decimal("99.60")


class TestCurrencyConversion:
    def test_eur_account_eurusd_conversion(self):
        spec = _spec("EURUSD", InstrumentType.FOREX, Decimal("100000"), quote_currency="USD")
        sizer = PositionSizer(spec, "EUR", rates={"USD": Decimal("0.92")}, **LOT_KW)
        p = _params("LONG", Decimal("1.1000"), Decimal("1.0950"), account_currency="EUR", rates={"USD": Decimal("0.92")})
        res = sizer.size(p, test_policy(), Decimal("10000.00"), Decimal("10000.00"))
        assert res.volume == Decimal("0.21")
        assert res.monetary_risk == Decimal("0.21") * Decimal("460")
        assert res.monetary_risk <= Decimal("100.00")

    def test_missing_conversion_rate_rejected(self):
        spec = _spec("EURUSD", InstrumentType.FOREX, Decimal("100000"), quote_currency="USD")
        sizer = PositionSizer(spec, "EUR", rates={}, **LOT_KW)
        p = _params("LONG", Decimal("1.1000"), Decimal("1.0950"), account_currency="EUR", rates={})
        res = sizer.size(p, test_policy(), Decimal("10000.00"), Decimal("10000.00"))
        assert res.volume is None
        assert any("convert" in r.lower() for r in res.reasons)


class TestMissingSpecs:
    def test_missing_contract_size_rejected(self):
        spec = InstrumentSpec(
            canonical_symbol="EURUSD", name="EURUSD",
            instrument_type=InstrumentType.FOREX,
            contract_size=None, tick_size=Decimal("0.00001"),
            volume_type=VolumeType.TICK,
        )
        sizer = PositionSizer(spec, "USD", **LOT_KW)
        p = _params("LONG", Decimal("1.1000"), Decimal("1.0950"))
        res = sizer.size(p, test_policy(), Decimal("10000.00"), Decimal("10000.00"))
        assert res.volume is None
        assert any("contract size" in r.lower() for r in res.reasons)


class TestRiskAmount:
    def test_percent_equity(self):
        assert risk_amount_from_policy(
            Decimal("10000"), Decimal("10000"), test_policy()
        ) == Decimal("100.00")

    def test_fixed_monetary_cap(self):
        policy = test_policy()
        policy = policy.__class__(
            version=policy.version, enabled=policy.enabled,
            sizing_method=__import__("src.risk_management.config", fromlist=["SizingMethod"]).SizingMethod.FIXED_MONETARY,
            risk_per_trade_percent=policy.risk_per_trade_percent,
            fixed_risk_amount=Decimal("50.00"),
            min_reward_to_risk=policy.min_reward_to_risk,
            max_volume=policy.max_volume,
            default_stop_method=policy.default_stop_method,
            atr_multiplier=policy.atr_multiplier,
            min_stop_distance=policy.min_stop_distance,
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
        assert risk_amount_from_policy(Decimal("10000"), Decimal("10000"), policy) == Decimal("50.00")

    def test_quote_to_account_rate_same_currency(self):
        assert quote_to_account_rate("USD", "USD", {}) == Decimal("1")

    def test_quote_to_account_rate_missing(self):
        assert quote_to_account_rate("USD", "EUR", {}) is None
