"""Tests for walk-forward splitting and out-of-sample evaluation."""

from __future__ import annotations

from decimal import Decimal

from src.backtesting.config import AccountConfig, test_backtest_config
from src.backtesting.walk_forward import rolling_windows, run_walk_forward
from src.market_data.models import MarketTimeframe
from tests.backtesting.conftest import make_bars, relaxed_risk_policy


def test_rolling_windows_chronological():
    bars = make_bars([1.10 + i * 0.001 for i in range(100)], symbol="EURUSD")
    windows = rolling_windows(bars, train_size=40, test_size=20, step=20)
    assert len(windows) == 3
    # Chronological order preserved.
    for w in windows:
        assert w.train_bars[-1].timestamp < w.test_bars[0].timestamp
        assert w.test_bars == sorted(w.test_bars, key=lambda b: b.timestamp)


def test_rolling_windows_no_shuffle():
    bars = make_bars([1.10 + i * 0.001 for i in range(60)], symbol="EURUSD")
    windows = rolling_windows(bars, train_size=30, test_size=15, step=15)
    for w in windows:
        # Train and test are contiguous slices of the original order.
        assert [b.timestamp for b in w.train_bars] == sorted(b.timestamp for b in w.train_bars)


def test_rolling_windows_invalid_sizes():
    bars = make_bars([1.10] * 10, symbol="EURUSD")
    import pytest
    with pytest.raises(ValueError):
        rolling_windows(bars, train_size=0, test_size=5)


def test_run_walk_forward_returns_windows():
    bars = make_bars([1.10 + (i % 5) * 0.001 for i in range(120)], symbol="EURUSD")
    cfg = test_backtest_config(overrides={
        "account": AccountConfig(starting_balance=Decimal("100000"), currency="USD", leverage=Decimal("30")),
        "risk_policy": relaxed_risk_policy(),
    })
    result = run_walk_forward(bars, "EURUSD", MarketTimeframe.H1, cfg, train_size=50, test_size=20, step=20)
    assert result["aggregate"]["num_windows"] >= 2
    for w in result["windows"]:
        assert "test_start" in w
        assert "oos_net_profit" in w