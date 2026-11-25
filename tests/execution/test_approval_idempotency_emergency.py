"""Phase 9 execution tests — approval, idempotency, emergency stop, order builder."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import shutil

import pytest

from src.execution.approval import ApprovalManager, ApprovalDecision
from src.execution.emergency_stop import EmergencyStop
from src.execution.execution_journal import ExecutionJournal
from src.execution.idempotency import IdempotencyManager
from src.execution.models import compute_fingerprint, ExecutionState
from src.execution.order_builder import OrderBuilder


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------

def test_approval_one_time():
    mgr = ApprovalManager(ttl_seconds=300)
    chal = mgr.create_challenge(
        signal_id="sig-1", symbol="EURUSD", side="LONG",
        volume=Decimal("0.01"), entry_price=Decimal("1.0850"),
        stop_loss_price=Decimal("1.0800"), take_profit_price=Decimal("1.0900"),
        magic_number=12345, mode="DEMO_MANUAL",
        preview={"instrument": "EURUSD"},
    )
    dec = mgr.approve(chal.token)
    assert dec.approved is True
    # Second approve is idempotent (already authorized).
    dec2 = mgr.approve(chal.token)
    assert dec2.approved is True
    assert "already" in dec2.reason.lower()
    # Submission consumes the approval (one-time).
    dec3 = mgr.validate_for_submission(
        signal_id="sig-1", symbol="EURUSD", side="LONG",
        volume=Decimal("0.01"), entry_price=Decimal("1.0850"),
        stop_loss_price=Decimal("1.0800"), take_profit_price=Decimal("1.0900"),
        magic_number=12345, mode="DEMO_MANUAL", token=chal.token,
    )
    assert dec3.approved is True
    # Re-submission with same token is rejected (already used).
    dec4 = mgr.validate_for_submission(
        signal_id="sig-1", symbol="EURUSD", side="LONG",
        volume=Decimal("0.01"), entry_price=Decimal("1.0850"),
        stop_loss_price=Decimal("1.0800"), take_profit_price=Decimal("1.0900"),
        magic_number=12345, mode="DEMO_MANUAL", token=chal.token,
    )
    assert dec4.approved is False
    assert "already used" in dec4.reason


def test_approval_expired():
    mgr = ApprovalManager(ttl_seconds=0)  # already expired
    chal = mgr.create_challenge(
        signal_id="sig-1", symbol="EURUSD", side="LONG",
        volume=Decimal("0.01"), entry_price=Decimal("1.0850"),
        stop_loss_price=None, take_profit_price=None,
        magic_number=12345, mode="DEMO_MANUAL",
        preview={"instrument": "EURUSD"},
    )
    dec = mgr.approve(chal.token)
    assert dec.approved is False
    assert dec.expired is True


def test_approval_bound_to_fingerprint_invalidates_on_change():
    mgr = ApprovalManager(ttl_seconds=300)
    chal = mgr.create_challenge(
        signal_id="sig-1", symbol="EURUSD", side="LONG",
        volume=Decimal("0.01"), entry_price=Decimal("1.0850"),
        stop_loss_price=Decimal("1.0800"), take_profit_price=Decimal("1.0900"),
        magic_number=12345, mode="DEMO_MANUAL",
        preview={"instrument": "EURUSD"},
    )
    mgr.approve(chal.token)
    # Changed volume -> different fingerprint -> no valid approval.
    dec = mgr.validate_for_submission(
        signal_id="sig-1", symbol="EURUSD", side="LONG",
        volume=Decimal("0.02"), entry_price=Decimal("1.0850"),
        stop_loss_price=Decimal("1.0800"), take_profit_price=Decimal("1.0900"),
        magic_number=12345, mode="DEMO_MANUAL",
    )
    assert dec.approved is False


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_idempotency_duplicate_detection():
    journal = ExecutionJournal(directory=".test_journal_dup")
    mgr = IdempotencyManager(journal)
    fp = compute_fingerprint(
        signal_id="sig-1", symbol="EURUSD", side="LONG",
        volume=Decimal("0.01"), entry_price=Decimal("1.0850"),
        stop_loss_price=Decimal("1.0800"), take_profit_price=Decimal("1.0900"),
        magic_number=12345, mode="PAPER",
    )
    r1 = mgr.check_duplicate(
        signal_id="sig-1", symbol="EURUSD", side="LONG",
        volume=Decimal("0.01"), entry_price=Decimal("1.0850"),
        stop_loss_price=Decimal("1.0800"), take_profit_price=Decimal("1.0900"),
        magic_number=12345, mode="PAPER",
    )
    assert r1.duplicate is False
    mgr.register_pending(fp, "exec-1")
    r2 = mgr.check_duplicate(
        signal_id="sig-1", symbol="EURUSD", side="LONG",
        volume=Decimal("0.01"), entry_price=Decimal("1.0850"),
        stop_loss_price=Decimal("1.0800"), take_profit_price=Decimal("1.0900"),
        magic_number=12345, mode="PAPER",
    )
    assert r2.duplicate is True
    assert r2.existing_execution_id == "exec-1"


# ---------------------------------------------------------------------------
# Emergency stop
# ---------------------------------------------------------------------------

def test_emergency_stop_blocks_execution():
    shutil.rmtree(".test_emergency_1", ignore_errors=True)
    es = EmergencyStop(directory=".test_emergency_1")
    assert es.is_execution_blocked() is False
    es.activate_global_lock()
    assert es.is_execution_blocked() is True
    es.deactivate_global_lock()
    assert es.is_execution_blocked() is False


def test_emergency_stop_new_entry_stop():
    es = EmergencyStop(directory=".test_emergency_2")
    es.activate_new_entry_stop()
    assert es.is_execution_blocked() is True


def test_emergency_daily_order_limit():
    es = EmergencyStop(directory=".test_emergency_3")
    es.state.max_demo_orders_per_day = 5
    assert es.check_daily_order_limit(4) is False
    assert es.check_daily_order_limit(5) is True


# ---------------------------------------------------------------------------
# Order builder
# ---------------------------------------------------------------------------

def test_builder_long_uses_ask():
    b = OrderBuilder(magic_number=12345)
    res = b.build_market_order(
        symbol="EURUSD", side="LONG", volume=Decimal("0.01"),
        entry_reference_price=Decimal("1.0850"),
        stop_loss_price=Decimal("1.0800"), take_profit_price=Decimal("1.0900"),
        tick_bid=Decimal("1.0849"), tick_ask=Decimal("1.0851"),
        price_precision=5, tick_size=Decimal("0.00001"),
        lot_step=Decimal("0.01"), min_lot=Decimal("0.01"), max_lot=Decimal("100.0"),
    )
    assert res.normalized_entry_price == Decimal("1.0851")  # ASK


def test_builder_short_uses_bid():
    b = OrderBuilder(magic_number=12345)
    res = b.build_market_order(
        symbol="EURUSD", side="SHORT", volume=Decimal("0.01"),
        entry_reference_price=Decimal("1.0850"),
        stop_loss_price=Decimal("1.0900"), take_profit_price=Decimal("1.0800"),
        tick_bid=Decimal("1.0849"), tick_ask=Decimal("1.0851"),
        price_precision=5, tick_size=Decimal("0.00001"),
        lot_step=Decimal("0.01"), min_lot=Decimal("0.01"), max_lot=Decimal("100.0"),
    )
    assert res.normalized_entry_price == Decimal("1.0849")  # BID


def test_builder_volume_rounded_down_never_up():
    b = OrderBuilder(magic_number=12345)
    res = b.build_market_order(
        symbol="EURUSD", side="LONG", volume=Decimal("0.015"),
        entry_reference_price=Decimal("1.0850"),
        stop_loss_price=Decimal("1.0800"), take_profit_price=Decimal("1.0900"),
        tick_bid=Decimal("1.0849"), tick_ask=Decimal("1.0851"),
        price_precision=5, tick_size=Decimal("0.00001"),
        lot_step=Decimal("0.01"), min_lot=Decimal("0.01"), max_lot=Decimal("100.0"),
    )
    assert res.normalized_volume == Decimal("0.01")  # rounded down
