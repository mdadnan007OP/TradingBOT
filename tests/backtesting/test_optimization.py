"""Tests for controlled parameter optimization."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.backtesting.config import AccountConfig, test_backtest_config
from src.backtesting.optimization import best_candidate, grid_search, robustness_score
from src.market_data.models import MarketTimeframe
from tests.backtesting.conftest import make_bars, relaxed_risk_policy


def _config():
    return test_backtest_config(overrides={
        "account": AccountConfig(starting_balance=Decimal("100000"), currency="USD", leverage=Decimal("30")),
        "risk_policy": relaxed_risk_policy(),
        "strategies": ["S"],
    })


def test_robustness_score_penalizes_low_trades():
    good = {"total_trades": 50, "net_return_percent": 10.0, "max_drawdown_percent": 5.0, "profit_factor": 1.5}
    poor = {"total_trades": 3, "net_return_percent": 100.0, "max_drawdown_percent": 1.0, "profit_factor": 5.0}
    assert robustness_score(poor) == float("-inf")
    assert robustness_score(good) > 0


def test_robustness_score_penalizes_drawdown():
    low_dd = {"total_trades": 50, "net_return_percent": 10.0, "max_drawdown_percent": 2.0, "profit_factor": 1.5}
    high_dd = {"total_trades": 50, "net_return_percent": 10.0, "max_drawdown_percent": 20.0, "profit_factor": 1.5}
    assert robustness_score(low_dd) > robustness_score(high_dd)


def test_grid_search_isolates_original_config():
    bars = make_bars([1.10 + (i % 4) * 0.001 for i in range(80)], symbol="EURUSD")
    cfg = _config()
    original_params = dict(cfg.strategy_parameters)
    grid_search(bars, "EURUSD", MarketTimeframe.H1, cfg, "S", {"fast": [5, 10]})
    # Original config must be unchanged.
    assert cfg.strategy_parameters == original_params


def test_grid_search_returns_sorted_candidates():
    bars = make_bars([1.10 + (i % 4) * 0.001 for i in range(80)], symbol="EURUSD")
    results = grid_search(bars, "EURUSD", MarketTimeframe.H1, _config(), "S", {"fast": [5, 10], "slow": [20, 30]})
    assert len(results) == 4
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_grid_search_empty_grid_raises():
    bars = make_bars([1.10] * 10, symbol="EURUSD")
    with pytest.raises(ValueError):
        grid_search(bars, "EURUSD", MarketTimeframe.H1, _config(), "S", {})


def test_best_candidate():
    results = [
        {"params": {}, "score": float("-inf"), "summary": {}},
        {"params": {}, "score": 1.0, "summary": {}},
        {"params": {}, "score": 3.0, "summary": {}},
    ]
    best = best_candidate(results)
    assert best["score"] == 3.0