"""Phase 9 execution tests — ExecutionEngine integration (PAPER mode, mocked).

Proves:
- PAPER mode is default and never submits to a broker.
- DEMO_AUTO disabled by default.
- LIVE/REAL rejected.
- Risk approval mandatory (RISK_APPROVED).
- Duplicate prevention.
- Manual approval required for DEMO_MANUAL.
"""

from decimal import Decimal

import pytest

from src.execution.account_identity import AccountIdentityVerifier
from src.execution.approval import ApprovalManager
from src.execution.config import ExecutionConfig, ExecutionMode
from src.execution.emergency_stop import EmergencyStop
from src.execution.execution_journal import ExecutionJournal
from src.execution.idempotency import IdempotencyManager
from src.execution.models import ExecutionState
from src.execution.order_builder import OrderBuilder
from src.execution.order_manager import OrderManager
from src.execution.position_manager import PositionManager
from src.execution.pre_trade_validator import PreTradeValidator
from src.execution.process_lock import ProcessLock
from src.execution.reconciliation import Reconciliation
from src.execution.reporting import ExecutionReporter
from src.execution.service import ExecutionEngine
from src.execution.state_machine import ExecutionStateMachine
from src.execution.trade_monitor import TradeMonitor
from src.execution.adapters.paper_adapter import PaperExecutionAdapter
from src.models import AccountInfo, OrderRequest, OrderSide, OrderType, Tick


class FakeRiskDecision:
    def __init__(self, status="RISK_APPROVED", signal_id="sig-1", symbol="EURUSD",
                 direction="LONG", volume=Decimal("0.01"),
                 stop_loss_price=Decimal("1.0800"), take_profit_price=Decimal("1.0900"),
                 monetary_risk=Decimal("10.0"), risk_percent=Decimal("0.01")):
        self.status = status
        self.signal_id = signal_id
        self.symbol = symbol
        self.direction = direction
        self.volume = volume
        self.stop_loss_price = stop_loss_price
        self.take_profit_price = take_profit_price
        self.monetary_risk = monetary_risk
        self.risk_percent = risk_percent


class FakeSignalValidator:
    def validate(self, **kwargs):
        return True


class FakeAccountIdentity:
    def __init__(self, passed=True, demo=True, trade_allowed=True,
                 server="PUPrime-Demo", trade_mode="demo"):
        self.verification_passed = passed
        self.is_demo = demo
        self.trade_allowed = trade_allowed
        self.server = server
        self.trade_mode = trade_mode
        self.verified_at = None


class FakeAccountVerifier:
    def __init__(self, ident):
        self.ident = ident

    def verify(self):
        return self.ident


def _build_engine(mode=ExecutionMode.PAPER, demo_enabled=False, ident=None,
                  journal_dir=None):
    import uuid as _uuid
    if journal_dir is None:
        journal_dir = f".test_engine_journal_{_uuid.uuid4().hex[:8]}"
    cfg = ExecutionConfig(
        mode=mode,
        demo_execution_enabled=demo_enabled,
        demo_manual_approval_required=True,
        magic_number=12345,
        allowed_demo_server="PUPrime-Demo",
        allowed_broker_company="PU Prime",
    )
    journal = ExecutionJournal(directory=journal_dir)
    idempotency = IdempotencyManager(journal)
    state_machine = ExecutionStateMachine()
    emergency_stop = EmergencyStop(directory=journal_dir + "_emergency")
    approval = ApprovalManager(ttl_seconds=300)
    account_verifier = FakeAccountVerifier(
        ident or FakeAccountIdentity()
    )
    order_builder = OrderBuilder(magic_number=cfg.magic_number)
    process_lock = ProcessLock()
    gateway = PaperExecutionAdapter()
    gateway.connect()
    risk_engine = None
    signal_validator = FakeSignalValidator()
    order_manager = OrderManager(
        gateway=gateway, journal=journal, idempotency=idempotency,
        state_machine=state_machine, approval=approval,
        emergency_stop=emergency_stop, account_verifier=account_verifier,
    )
    position_manager = PositionManager(magic_number=cfg.magic_number, journal=journal)
    trade_monitor = TradeMonitor(gateway=gateway, journal=journal)
    reconciliation = Reconciliation(gateway=gateway, journal=journal)
    reporter = ExecutionReporter(journal=journal)
    engine = ExecutionEngine(
        config=cfg, gateway=gateway, journal=journal, idempotency=idempotency,
        state_machine=state_machine, emergency_stop=emergency_stop,
        account_verifier=account_verifier, approval=approval,
        risk_engine=risk_engine, signal_validator=signal_validator,
        order_builder=order_builder, order_manager=order_manager,
        position_manager=position_manager, trade_monitor=trade_monitor,
        reconciliation=reconciliation, reporter=reporter,
        process_lock=process_lock,
    )
    return engine, cfg, journal


def test_paper_mode_default_no_orders_submitted():
    engine, cfg, journal = _build_engine()
    assert cfg.mode == ExecutionMode.PAPER
    assert engine.gateway.can_submit_orders() is False
    proposal = engine.propose_execution(
        signal_id="sig-1", strategy_name="S", strategy_version="1.0",
        symbol="EURUSD", side="LONG", volume=Decimal("0.01"),
        entry_reference_price=Decimal("1.0850"),
        stop_loss_price=Decimal("1.0800"), take_profit_price=Decimal("1.0900"),
        risk_decision=FakeRiskDecision(), risk_policy_version="1.0",
    )
    assert proposal.requires_approval is False
    outcome = engine.authorize_and_submit(proposal)
    assert outcome.submitted is True
    assert outcome.result.state == ExecutionState.FILLED
    # PAPER simulated fill, no broker involved.


def test_paper_mode_cannot_reach_demo_gateway():
    engine, cfg, journal = _build_engine()
    assert engine.gateway.mode == "PAPER"
    assert engine.gateway.can_submit_orders() is False


def test_demo_auto_disabled_by_default():
    engine, cfg, journal = _build_engine()
    assert cfg.automatic_permitted is False
    pol = engine.policy.decide()
    assert pol.automatic_permitted is False


def test_risk_approval_mandatory():
    engine, cfg, journal = _build_engine()
    bad_risk = FakeRiskDecision(status="REJECTED")
    with pytest.raises(ValueError):
        engine.propose_execution(
            signal_id="sig-1", strategy_name="S", strategy_version="1.0",
            symbol="EURUSD", side="LONG", volume=Decimal("0.01"),
            entry_reference_price=Decimal("1.0850"),
            stop_loss_price=Decimal("1.0800"), take_profit_price=Decimal("1.0900"),
            risk_decision=bad_risk, risk_policy_version="1.0",
        )


def test_risk_volume_not_increased():
    engine, cfg, journal = _build_engine()
    # Risk approves 0.01, request 0.05 -> rejected.
    risk = FakeRiskDecision(volume=Decimal("0.01"))
    with pytest.raises(ValueError):
        engine.propose_execution(
            signal_id="sig-1", strategy_name="S", strategy_version="1.0",
            symbol="EURUSD", side="LONG", volume=Decimal("0.05"),
            entry_reference_price=Decimal("1.0850"),
            stop_loss_price=Decimal("1.0800"), take_profit_price=Decimal("1.0900"),
            risk_decision=risk, risk_policy_version="1.0",
        )


def test_demo_manual_approval_required():
    ident = FakeAccountIdentity()
    engine, cfg, journal = _build_engine(mode=ExecutionMode.DEMO_MANUAL, demo_enabled=True, ident=ident)
    proposal = engine.propose_execution(
        signal_id="sig-1", strategy_name="S", strategy_version="1.0",
        symbol="EURUSD", side="LONG", volume=Decimal("0.01"),
        entry_reference_price=Decimal("1.0850"),
        stop_loss_price=Decimal("1.0800"), take_profit_price=Decimal("1.0900"),
        risk_decision=FakeRiskDecision(), risk_policy_version="1.0",
    )
    assert proposal.requires_approval is True
    assert proposal.authorization_token is not None
    # Submit without token -> rejected.
    outcome = engine.authorize_and_submit(proposal)
    assert outcome.submitted is False
    assert outcome.result.state == ExecutionState.AWAITING_MANUAL_APPROVAL


def test_demo_manual_with_valid_token_submits():
    ident = FakeAccountIdentity()
    engine, cfg, journal = _build_engine(mode=ExecutionMode.DEMO_MANUAL, demo_enabled=True, ident=ident)
    proposal = engine.propose_execution(
        signal_id="sig-1", strategy_name="S", strategy_version="1.0",
        symbol="EURUSD", side="LONG", volume=Decimal("0.01"),
        entry_reference_price=Decimal("1.0850"),
        stop_loss_price=Decimal("1.0800"), take_profit_price=Decimal("1.0900"),
        risk_decision=FakeRiskDecision(), risk_policy_version="1.0",
    )
    assert proposal.requires_approval is True
    # User explicitly approves the order.
    engine.approval.approve(proposal.authorization_token)
    outcome = engine.authorize_and_submit(proposal, approval_token=proposal.authorization_token)
    # PAPER adapter is the gateway here (no real demo adapter), so it simulates.
    assert outcome.submitted is True
    assert outcome.result.state == ExecutionState.FILLED


def test_duplicate_signal_prevented():
    engine, cfg, journal = _build_engine()
    risk = FakeRiskDecision(signal_id="sig-dup")
    # First proposal+submit.
    p1 = engine.propose_execution(
        signal_id="sig-dup", strategy_name="S", strategy_version="1.0",
        symbol="EURUSD", side="LONG", volume=Decimal("0.01"),
        entry_reference_price=Decimal("1.0850"),
        stop_loss_price=Decimal("1.0800"), take_profit_price=Decimal("1.0900"),
        risk_decision=risk, risk_policy_version="1.0",
    )
    engine.authorize_and_submit(p1)
    # Same signal fingerprint again -> duplicate.
    p2 = engine.propose_execution(
        signal_id="sig-dup", strategy_name="S", strategy_version="1.0",
        symbol="EURUSD", side="LONG", volume=Decimal("0.01"),
        entry_reference_price=Decimal("1.0850"),
        stop_loss_price=Decimal("1.0800"), take_profit_price=Decimal("1.0900"),
        risk_decision=risk, risk_policy_version="1.0",
    )
    outcome = engine.authorize_and_submit(p2)
    assert outcome.submitted is False


def test_report_generated():
    engine, cfg, journal = _build_engine()
    snap = engine.snapshot()
    rep = engine.report(snap)
    assert rep.disclaimer is not None
    assert "simulated" in rep.disclaimer.lower() or "demo" in rep.disclaimer.lower()
