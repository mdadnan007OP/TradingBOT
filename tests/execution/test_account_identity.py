"""Phase 9 execution tests — account identity verification (mocked MT5).

MT5 trade_mode: 0=demo, 1=contest, 2=real.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.execution.account_identity import AccountIdentityVerifier
from src.execution.config import ExecutionConfig, ExecutionMode
from src.broker.mt5.connection import MT5AccountInfo


class FakeAccountInfo:
    def __init__(self, trade_mode=0, server="PUPrime-Demo", company="PU Prime",
                 currency="USD", trade_allowed=True, login=1):
        # MT5 trade_mode: 0=demo, 1=contest, 2=real
        self.trade_mode = trade_mode
        self.server = server
        self.company = company
        self.currency = currency
        self.trade_allowed = trade_allowed
        self.login = login


class FakeMT5Module:
    def __init__(self, account):
        self.account = account

    def account_info(self):
        return self.account

    def terminal_info(self):
        return SimpleNamespace(connected=True, company="PU Prime", name="MT5", version="1", build=1, path="")


class FakeConnection:
    def __init__(self, account):
        self._mt5_module = FakeMT5Module(account)
        self._initialized = True
        self.terminal_info = SimpleNamespace(connected=True, company="PU Prime")

    def check_connection(self):
        return self._initialized


def _verifier(account, server="PUPrime-Demo", company="PU Prime"):
    cfg = ExecutionConfig(
        mode=ExecutionMode.DEMO_MANUAL,
        demo_execution_enabled=True,
        magic_number=12345,
        allowed_demo_server=server,
        allowed_broker_company=company,
    )
    return AccountIdentityVerifier(connection=FakeConnection(account), config=cfg)


def test_demo_account_accepted():
    v = _verifier(FakeAccountInfo(trade_mode=0))
    ident = v.verify()
    assert ident.verification_passed is True
    assert ident.is_demo is True
    assert ident.trade_mode == "demo"


def test_real_account_rejected():
    v = _verifier(FakeAccountInfo(trade_mode=2))
    ident = v.verify()
    assert ident.verification_passed is False
    assert ident.is_demo is False
    assert "real" in (ident.rejection_reason or "").lower()


def test_contest_account_rejected():
    v = _verifier(FakeAccountInfo(trade_mode=1))
    ident = v.verify()
    assert ident.verification_passed is False
    assert "contest" in (ident.rejection_reason or "").lower()


def test_wrong_server_rejected():
    v = _verifier(FakeAccountInfo(trade_mode=0, server="Other-Server"), server="PUPrime-Demo")
    ident = v.verify()
    assert ident.verification_passed is False
    assert "server" in (ident.rejection_reason or "").lower()


def test_wrong_company_rejected():
    v = _verifier(FakeAccountInfo(trade_mode=0, company="Other Broker"), company="PU Prime")
    ident = v.verify()
    assert ident.verification_passed is False
    assert "company" in (ident.rejection_reason or "").lower()


def test_terminal_not_connected_rejected():
    cfg = ExecutionConfig(
        mode=ExecutionMode.DEMO_MANUAL,
        demo_execution_enabled=True,
        magic_number=12345,
        allowed_demo_server="PUPrime-Demo",
    )
    conn = FakeConnection(FakeAccountInfo())
    conn._initialized = False
    v = AccountIdentityVerifier(connection=conn, config=cfg)
    ident = v.verify()
    assert ident.verification_passed is False


def test_no_raw_login_logged():
    v = _verifier(FakeAccountInfo(trade_mode=0, login=987654321))
    ident = v.verify()
    # Fingerprint should not equal raw login.
    assert ident.identity_fingerprint != "987654321"
    assert len(ident.identity_fingerprint) == 64  # sha256 hex
