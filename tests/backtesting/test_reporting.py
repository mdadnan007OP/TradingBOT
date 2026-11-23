"""Tests for reporting and persistence."""

from __future__ import annotations

import json
import os
from decimal import Decimal

from src.backtesting.models import BacktestResult, ClosedTrade, EquityPoint, ExitReason, OrderSide
from src.backtesting.persistence import load_result, save_result
from src.backtesting.reporting import (
    equity_curve_to_csv,
    format_summary,
    monthly_performance,
    report_to_dict,
    report_to_json,
    trades_to_csv,
    write_all,
)
from tests.backtesting.conftest import BASE
from datetime import timedelta


def _result():
    trades = [ClosedTrade(
        trade_id="t1", position_id="p1", symbol="EURUSD", side=OrderSide.LONG,
        volume=Decimal("1"), entry_price=Decimal("1.1000"), exit_price=Decimal("1.1010"),
        entry_time=BASE, exit_time=BASE + timedelta(hours=1), exit_reason=ExitReason.TAKE_PROFIT,
        strategy_name="S", gross_pnl_quote=Decimal("100"), net_pnl_account=Decimal("100"),
    )]
    curve = [
        EquityPoint(timestamp=BASE, equity=Decimal("10000"), balance=Decimal("10000")),
        EquityPoint(timestamp=BASE + timedelta(hours=1), equity=Decimal("10100"), balance=Decimal("10100")),
    ]
    return BacktestResult(
        config_name="unit", symbols=["EURUSD"], timeframes=["H1"],
        start_time=BASE, end_time=BASE + timedelta(hours=1),
        equity_curve=curve, trades=trades,
        metadata={"config": {"account": {"starting_balance": "10000"}}},
    )


def test_report_to_dict():
    d = report_to_dict(_result())
    assert d["config"] == "unit"
    assert d["performance"]["ending_equity"] == 10100.0
    assert d["performance"]["trade_stats"]["total_trades"] == 1


def test_report_to_json(tmp_path):
    p = str(tmp_path / "r.json")
    report_to_json(_result(), p)
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["config"] == "unit"
    assert "disclaimer" in data


def test_trades_to_csv(tmp_path):
    p = str(tmp_path / "t.csv")
    trades_to_csv(_result().trades, p)
    with open(p, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    assert len(lines) == 2  # header + 1 trade
    assert "net_pnl_account" in lines[0]


def test_equity_curve_to_csv(tmp_path):
    p = str(tmp_path / "e.csv")
    equity_curve_to_csv(_result().equity_curve, p)
    with open(p, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    assert len(lines) == 3


def test_monthly_performance():
    mp = monthly_performance(_result().equity_curve)
    assert "2026-01" in mp


def test_format_summary():
    text = format_summary(_result())
    assert "Backtest: unit" in text
    assert "Disclaimer" in text


def test_write_all(tmp_path):
    paths = write_all(_result(), str(tmp_path))
    assert os.path.exists(paths["json"])
    assert os.path.exists(paths["trades"])
    assert os.path.exists(paths["equity"])


def test_save_and_load_roundtrip(tmp_path):
    p = str(tmp_path / "saved.json")
    save_result(_result(), p)
    loaded = load_result(p)
    assert loaded.config_name == "unit"
    assert loaded.total_trades == 1
    assert loaded.trades[0].net_pnl_account == Decimal("100")
    assert loaded.equity_curve[-1].equity == Decimal("10100")