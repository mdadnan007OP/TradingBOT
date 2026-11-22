"""Phase 6 risk management tests — shared fixtures."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.market_data.models import InstrumentSpec, InstrumentType, VolumeType
from src.risk_management.base import AccountSnapshot, RiskParameters
from src.risk_management.config import RiskPolicy, SizingMethod, StopMethod, test_policy


@pytest.fixture
def usd_account():
    return AccountSnapshot(
        login=123456,
        name="Test USD Account",
        server="Test-Server",
        currency="USD",
        balance=Decimal("10000.00"),
        equity=Decimal("10000.00"),
        margin=Decimal("0"),
        free_margin=Decimal("10000.00"),
        trade_allowed=True,
        trade_mode="demo",
        timestamp=datetime.now(timezone.utc),
        data_source="mock",
    )


@pytest.fixture
def eur_account():
    return AccountSnapshot(
        login=123457,
        name="Test EUR Account",
        server="Test-Server",
        currency="EUR",
        balance=Decimal("10000.00"),
        equity=Decimal("10000.00"),
        margin=Decimal("0"),
        free_margin=Decimal("10000.00"),
        trade_allowed=True,
        trade_mode="demo",
        timestamp=datetime.now(timezone.utc),
        data_source="mock",
    )


@pytest.fixture
def policy():
    return test_policy()


@pytest.fixture
def eurusd_spec():
    return InstrumentSpec(
        canonical_symbol="EURUSD",
        name="Euro vs US Dollar",
        instrument_type=InstrumentType.FOREX,
        base_currency="EUR",
        quote_currency="USD",
        price_precision=5,
        tick_size=Decimal("0.00001"),
        pip_size=Decimal("0.0001"),
        contract_size=Decimal("100000"),
        volume_type=VolumeType.TICK,
    )


@pytest.fixture
def xauusd_spec():
    return InstrumentSpec(
        canonical_symbol="XAUUSD",
        name="Gold vs US Dollar",
        instrument_type=InstrumentType.METAL,
        base_currency="XAU",
        quote_currency="USD",
        price_precision=2,
        tick_size=Decimal("0.01"),
        contract_size=Decimal("100"),
        volume_type=VolumeType.TICK,
    )


@pytest.fixture
def usdjpy_spec():
    return InstrumentSpec(
        canonical_symbol="USDJPY",
        name="US Dollar vs Japanese Yen",
        instrument_type=InstrumentType.FOREX,
        base_currency="USD",
        quote_currency="JPY",
        price_precision=3,
        tick_size=Decimal("0.001"),
        pip_size=Decimal("0.01"),
        contract_size=Decimal("100000"),
        volume_type=VolumeType.TICK,
    )


def long_params(symbol="EURUSD", entry=Decimal("1.1000"), stop=Decimal("1.0950"), **overrides):
    p = RiskParameters(
        signal_id="s1",
        symbol=symbol,
        instrument_type="forex",
        direction="LONG",
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


def short_params(symbol="EURUSD", entry=Decimal("1.1000"), stop=Decimal("1.1050"), **overrides):
    p = RiskParameters(
        signal_id="s2",
        symbol=symbol,
        instrument_type="forex",
        direction="SHORT",
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
