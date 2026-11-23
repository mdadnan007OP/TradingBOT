"""Tests for stress testing scenarios."""

from __future__ import annotations

from decimal import Decimal

from src.backtesting.config import (
    AccountConfig,
    CommissionConfig,
    CommissionModel,
    SlippageConfig,
    SlippageModel,
    SpreadConfig,
    test_backtest_config,
)
from src.backtesting.stress import (
    run_stress,
    stress_scenarios,
    _spread_multiplier,
    _slippage_points,
    _commission,
)
from src.market_data.models import MarketTimeframe
from tests.backtesting.conftest import make_bars, relaxed_risk_policy


def _config():
    return test_backtest_config(overrides={
        "account": AccountConfig(starting_balance=Decimal("100000"), currency="USD", leverage=Decimal("30")),
        "risk_policy": relaxed_risk_policy(),
    })


def test_spread_multiplier_increases_spread():
    cfg = test_backtest_config()
    cfg2 = _spread_multiplier(cfg, Decimal("2"))
    assert cfg2.execution.spread.fixed_spread["EURUSD"] == cfg.execution.spread.fixed_spread["EURUSD"] * 2


def test_slippage_points_sets_model():
    cfg = test_backtest_config()
    cfg2 = _slippage_points(cfg, {"EURUSD": Decimal("0.0002")})
    assert cfg2.execution.slippage.model == SlippageModel.FIXED_POINTS
    assert cfg2.execution.slippage.fixed_points["EURUSD"] == Decimal("0.0002")


def test_commission_sets_model():
    cfg = test_backtest_config()
    cfg2 = _commission(cfg, Decimal("7"))
    assert cfg2.execution.commission.model == CommissionModel.PER_LOT
    assert cfg2.execution.commission.per_lot == Decimal("7")


def test_stress_scenarios_exist():
    scenarios = stress_scenarios()
    assert "higher_spread_2x" in scenarios
    assert "slippage_1pip" in scenarios
    assert "commission_7_per_lot" in scenarios


def test_run_stress_returns_baseline_and_scenarios():
    bars = make_bars([1.10 + (i % 5) * 0.001 for i in range(80)], symbol="EURUSD")
    result = run_stress(bars, "EURUSD", MarketTimeframe.H1, _config())
    assert result["baseline"] is not None
    assert "higher_spread_2x" in result["scenarios"]
    assert "commission_7_per_lot" in result["scenarios"]


def test_stress_higher_costs_do_not_improve_pnl():
    bars = make_bars([1.10 + (i % 5) * 0.001 for i in range(80)], symbol="EURUSD")
    result = run_stress(bars, "EURUSD", MarketTimeframe.H1, _config())
    baseline = result["baseline"]["net_profit"]
    stressed = result["scenarios"]["higher_spread_5x"]["net_profit"]
    # Higher spread must never improve net profit versus baseline.
    assert stressed <= baseline + 1e-9