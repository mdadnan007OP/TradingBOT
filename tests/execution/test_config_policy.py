"""Phase 9 execution tests — config, policy, state machine."""

import os
from decimal import Decimal

import pytest

from src.execution.config import ExecutionConfig, ExecutionMode
from src.execution.execution_policy import ExecutionPolicy
from src.execution.state_machine import ExecutionState, ExecutionStateMachine


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def test_default_mode_is_paper(monkeypatch):
    monkeypatch.delenv("EXECUTION_MODE", raising=False)
    cfg = ExecutionConfig.from_env()
    assert cfg.mode == ExecutionMode.PAPER
    assert cfg.demo_trading_permitted is False
    assert cfg.automatic_permitted is False


def test_live_mode_rejected(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "LIVE")
    with pytest.raises(ValueError):
        ExecutionConfig.from_env()


def test_real_mode_rejected(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "REAL")
    with pytest.raises(ValueError):
        ExecutionConfig.from_env()


def test_demo_manual_requires_enable(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "DEMO_MANUAL")
    monkeypatch.delenv("DEMO_EXECUTION_ENABLED", raising=False)
    with pytest.raises(ValueError):
        ExecutionConfig.from_env()


def test_demo_auto_requires_env_and_flag(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "DEMO_AUTO")
    monkeypatch.delenv("DEMO_AUTOMATIC_ENABLED", raising=False)
    with pytest.raises(ValueError):
        ExecutionConfig.from_env()


def test_demo_auto_disabled_by_default(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "PAPER")
    cfg = ExecutionConfig.from_env()
    assert cfg.automatic_permitted is False


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

def test_policy_paper_default():
    cfg = ExecutionConfig(mode=ExecutionMode.PAPER)
    pol = ExecutionPolicy(cfg)
    d = pol.decide()
    assert d.permitted is True
    assert d.mode == "PAPER"
    assert d.requires_manual_approval is False


def test_policy_demo_manual_requires_enable():
    with pytest.raises(ValueError):
        ExecutionConfig(
            mode=ExecutionMode.DEMO_MANUAL,
            demo_execution_enabled=False,
            magic_number=12345,
            allowed_demo_server="PUPrime-Demo",
        )


def test_policy_demo_auto_disabled_without_flags():
    with pytest.raises(ValueError):
        ExecutionConfig(
            mode=ExecutionMode.DEMO_AUTO,
            demo_execution_enabled=True,
            demo_automatic_enabled=False,
            magic_number=12345,
            allowed_demo_server="PUPrime-Demo",
        )


def test_policy_demo_auto_enabled_with_both_flags():
    cfg = ExecutionConfig(
        mode=ExecutionMode.DEMO_AUTO,
        demo_execution_enabled=True,
        demo_automatic_enabled=True,
        magic_number=12345,
        allowed_demo_server="PUPrime-Demo",
    )
    pol = ExecutionPolicy(cfg, cli_demo_auto=True)
    d = pol.decide()
    assert d.permitted is True
    assert d.automatic_permitted is True


def test_live_trading_locked_always():
    cfg = ExecutionConfig(mode=ExecutionMode.PAPER)
    pol = ExecutionPolicy(cfg)
    assert pol.live_trading_locked() is True


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

def test_valid_transitions():
    sm = ExecutionStateMachine()
    assert sm.can_transition(ExecutionState.CREATED, ExecutionState.PENDING_VALIDATION)
    assert sm.can_transition(ExecutionState.PENDING_VALIDATION, ExecutionState.RISK_APPROVED)
    assert sm.can_transition(ExecutionState.RISK_APPROVED, ExecutionState.PRE_TRADE_CHECKED)
    assert sm.can_transition(ExecutionState.PRE_TRADE_CHECKED, ExecutionState.SUBMITTED)
    assert sm.can_transition(ExecutionState.SUBMITTED, ExecutionState.FILLED)


def test_invalid_transition_rejected():
    sm = ExecutionStateMachine()
    assert sm.can_transition(ExecutionState.CREATED, ExecutionState.FILLED) is False
    assert sm.can_transition(ExecutionState.FILLED, ExecutionState.SUBMITTED) is False


def test_terminal_states():
    assert ExecutionState.FILLED.is_terminal
    assert ExecutionState.REJECTED.is_terminal
    assert ExecutionState.CREATED.is_terminal is False
