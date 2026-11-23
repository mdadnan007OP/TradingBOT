"""Tests for cost models: spread, slippage, commission, swap, currency conversion."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from src.backtesting.commission_model import CommissionModel
from src.backtesting.config import (
    CommissionConfig,
    CommissionModel as CommissionModelEnum,
    SlippageConfig,
    SlippageModel as SlippageModelEnum,
    SpreadConfig,
    SwapConfig,
)
from src.backtesting.currency_conversion import CurrencyConverter
from src.backtesting.slippage_model import SlippageModel
from src.backtesting.spread_model import SpreadModel
from src.backtesting.swap_model import SwapModel

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


# --- Spread ---

def test_spread_fixed():
    sm = SpreadModel(SpreadConfig(fixed_spread={"EURUSD": Decimal("0.0002")}))
    q = sm.resolve("EURUSD", Decimal("1.1000"))
    assert q.spread == Decimal("0.0002")
    assert q.ask - q.bid == Decimal("0.0002")
    assert q.source == "fixed"


def test_spread_never_silently_zero():
    sm = SpreadModel(SpreadConfig())
    q = sm.resolve("UNKNOWN", Decimal("1.0"))
    # No spread configured → source is "none" (caller must warn), not silently zero.
    assert q.source == "none"


def test_spread_from_bar_bid_ask():
    from src.market_data.models import DataSource, MarketTimeframe, OHLCBar
    bar = OHLCBar(
        symbol="EURUSD", timeframe=MarketTimeframe.H1, timestamp=BASE,
        open=Decimal("1.1000"), high=Decimal("1.1010"), low=Decimal("1.0990"),
        close=Decimal("1.1005"), bid=Decimal("1.1004"), ask=Decimal("1.1006"),
        data_source=DataSource.HISTORICAL,
    )
    sm = SpreadModel(SpreadConfig())
    q = sm.resolve("EURUSD", Decimal("1.1005"), bar)
    assert q.source == "bid_ask"
    assert q.bid == Decimal("1.1004")
    assert q.ask == Decimal("1.1006")


def test_spread_from_bar_spread_field():
    from src.market_data.models import DataSource, MarketTimeframe, OHLCBar
    bar = OHLCBar(
        symbol="EURUSD", timeframe=MarketTimeframe.H1, timestamp=BASE,
        open=Decimal("1.1000"), high=Decimal("1.1010"), low=Decimal("1.0990"),
        close=Decimal("1.1000"), spread=Decimal("0.0003"),
        data_source=DataSource.HISTORICAL,
    )
    sm = SpreadModel(SpreadConfig(use_bar_bid_ask=False))
    q = sm.resolve("EURUSD", Decimal("1.1000"), bar)
    assert q.source == "bar_spread"
    assert q.ask - q.bid == Decimal("0.0003")


# --- Slippage ---

def test_slippage_fixed_points_adverse():
    sm = SlippageModel(SlippageConfig(
        model=SlippageModelEnum.FIXED_POINTS, fixed_points={"EURUSD": Decimal("0.0002")}
    ))
    buy = sm.apply("EURUSD", is_buy=True, price=Decimal("1.1000"))
    sell = sm.apply("EURUSD", is_buy=False, price=Decimal("1.1000"))
    assert buy.price == Decimal("1.1002")  # buy higher
    assert sell.price == Decimal("1.0998")  # sell lower


def test_slippage_none():
    sm = SlippageModel(SlippageConfig(model=SlippageModelEnum.NONE))
    r = sm.apply("EURUSD", is_buy=True, price=Decimal("1.1000"))
    assert r.price == Decimal("1.1000")
    assert r.slippage == Decimal("0")


# --- Commission ---

def test_commission_per_lot():
    cm = CommissionModel(CommissionConfig(model=CommissionModelEnum.PER_LOT, per_lot=Decimal("7")))
    assert cm.commission_for(Decimal("0.5")).amount == Decimal("3.5")
    assert cm.entry_and_exit(Decimal("0.5")) == Decimal("7")  # 2 sides


def test_commission_per_trade():
    cm = CommissionModel(CommissionConfig(model=CommissionModelEnum.PER_TRADE, per_trade=Decimal("5")))
    assert cm.entry_and_exit(Decimal("2.0")) == Decimal("5")


# --- Swap ---

def test_swap_disabled():
    sm = SwapModel(SwapConfig(enabled=False))
    r = sm.swap_for("EURUSD", True, Decimal("1"), 3)
    assert r.amount == Decimal("0")


def test_swap_enabled():
    sm = SwapModel(SwapConfig(
        enabled=True, long_points={"EURUSD": Decimal("-0.5")},
        point_value={"EURUSD": Decimal("1")},
    ))
    r = sm.swap_for("EURUSD", is_long=True, volume=Decimal("1"), nights=3)
    assert r.amount == Decimal("-1.5")  # credit (negative points)


def test_swap_triple_night():
    sm = SwapModel(SwapConfig(
        enabled=True, long_points={"EURUSD": Decimal("-0.5")},
        point_value={"EURUSD": Decimal("1")}, triple_days=[2],
    ))
    # Wednesday (weekday 2) held → triple.
    wed = datetime(2026, 1, 7, tzinfo=timezone.utc)
    r = sm.swap_for_period("EURUSD", True, Decimal("1"), 1, [wed])
    assert r.amount == Decimal("-1.5")


# --- Currency conversion ---

def test_currency_conversion_same():
    cc = CurrencyConverter(account_currency="USD")
    assert cc.convert(Decimal("100"), "USD") == Decimal("100")


def test_currency_conversion_rate():
    cc = CurrencyConverter(account_currency="USD", static_rates={"EUR": Decimal("1.10")})
    assert cc.convert(Decimal("100"), "EUR") == Decimal("110")


def test_currency_conversion_as_of():
    cc = CurrencyConverter(
        account_currency="USD",
        historical_rates={"EUR": [
            (datetime(2026, 1, 1, tzinfo=timezone.utc), Decimal("1.10")),
            (datetime(2026, 2, 1, tzinfo=timezone.utc), Decimal("1.20")),
        ]},
    )
    # As-of Jan 15 → uses Jan 1 rate (no future leak).
    assert cc.rate("EUR", datetime(2026, 1, 15, tzinfo=timezone.utc)) == Decimal("1.10")
    # As-of Feb 10 → uses Feb 1 rate.
    assert cc.rate("EUR", datetime(2026, 2, 10, tzinfo=timezone.utc)) == Decimal("1.20")


def test_currency_conversion_unavailable_returns_none():
    cc = CurrencyConverter(account_currency="USD")
    assert cc.convert(Decimal("100"), "GBP") is None