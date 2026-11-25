"""Phase 9 execution tests — PAPER adapter (simulated, no broker calls)."""

from decimal import Decimal

import pytest

from src.execution.adapters.paper_adapter import PaperExecutionAdapter
from src.execution.models import ExecutionState
from src.models import OrderSide, OrderType


def test_paper_adapter_never_submits_to_broker():
    adapter = PaperExecutionAdapter()
    assert adapter.can_submit_orders() is False
    assert adapter.mode == "PAPER"


def test_paper_simulated_fill():
    adapter = PaperExecutionAdapter()
    adapter.connect()
    from src.models import OrderRequest
    req = OrderRequest(
        symbol="EURUSD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=Decimal("0.01"),
        price=Decimal("1.0850"),
        stop_loss=Decimal("1.0800"),
        take_profit=Decimal("1.0900"),
        comment="paper test",
        magic_number=12345,
    )
    result = adapter.order_send(req)
    assert result.success is True
    assert result.state == ExecutionState.FILLED
    assert result.ticket is not None
    # PAPER never reaches a real broker: no order_send() call was made.


def test_paper_order_check_preflight_not_a_trade():
    adapter = PaperExecutionAdapter()
    adapter.connect()
    from src.models import OrderRequest
    req = OrderRequest(
        symbol="EURUSD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=Decimal("0.01"),
        price=Decimal("1.0850"),
    )
    res = adapter.order_check(req)
    assert res.success is True
    assert res.state == ExecutionState.ACCEPTED
    # order_check() success is NOT a trade execution.


def test_paper_invalid_volume_rejected():
    adapter = PaperExecutionAdapter()
    adapter.connect()
    from src.models import OrderRequest
    req = OrderRequest(
        symbol="EURUSD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=Decimal("0.001"),  # below min_lot 0.01
        price=Decimal("1.0850"),
    )
    res = adapter.order_send(req)
    assert res.success is False


def test_paper_report_disclaimer():
    adapter = PaperExecutionAdapter()
    adapter.connect()
    report = adapter.paper_report()
    assert report["mode"] == "PAPER"
    assert "disclaimer" in report
    assert "simulated" in report["disclaimer"].lower()


def test_paper_positions_tracked():
    adapter = PaperExecutionAdapter()
    adapter.connect()
    from src.models import OrderRequest
    req = OrderRequest(
        symbol="EURUSD",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=Decimal("0.01"),
        price=Decimal("1.0850"),
    )
    adapter.order_send(req)
    positions = adapter.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "EURUSD"
