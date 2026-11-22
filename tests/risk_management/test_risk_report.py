"""Risk report tests."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.risk_management.base import AccountSnapshot, RiskDecision, RiskDecisionStatus
from src.risk_management.models import (
    DailyPnLState,
    DrawdownState,
    ExposureSummary,
    RiskReport,
)
from src.risk_management.risk_report import decision_to_dict, format_decision_text, report_to_dict


def _decision():
    return RiskDecision(
        signal_id="s1",
        symbol="EURUSD",
        instrument_type="forex",
        direction="LONG",
        status=RiskDecisionStatus.APPROVED,
        rejection_reasons=[],
        warnings=[],
        volume=Decimal("0.20"),
        monetary_risk=Decimal("100.00"),
        risk_percent=Decimal("1.00"),
        stop_loss_price=Decimal("1.0950"),
        take_profit_price=Decimal("1.1100"),
        reward_to_risk=Decimal("2.0"),
        estimated_margin=Decimal("733.33"),
        account_timestamp=datetime.now(timezone.utc),
        policy_version="1.0.0",
        data_source="mock",
    )


def _account():
    return AccountSnapshot(
        login=1, name="t", server="t", currency="USD",
        balance=Decimal("10000"), equity=Decimal("10000"),
        margin=Decimal("0"), free_margin=Decimal("10000"),
        trade_allowed=True, trade_mode="demo",
        timestamp=datetime.now(timezone.utc), data_source="mock",
    )


class TestDecisionSerialization:
    def test_decision_to_dict(self):
        d = _decision()
        out = decision_to_dict(d)
        assert out["signal_id"] == "s1"
        assert out["status"] == "RISK_APPROVED"
        assert out["volume"] == "0.20"
        assert out["monetary_risk"] == "100.00"
        assert out["reward_to_risk"] == "2.0"

    def test_format_decision_text(self):
        text = format_decision_text(_decision())
        assert "RISK_APPROVED" in text
        assert "EURUSD" in text
        assert "LONG" in text


class TestReportSerialization:
    def test_report_to_dict(self):
        report = RiskReport(
            decision=_decision(),
            account_snapshot=_account(),
            drawdown_state=DrawdownState(
                equity_high_watermark=Decimal("10000"),
                balance_high_watermark=Decimal("10000"),
            ),
            daily_pnl_state=DailyPnLState(
                starting_balance=Decimal("10000"),
                starting_equity=Decimal("10000"),
            ),
            exposure_summary=ExposureSummary(
                total_positions=1, total_notional=Decimal("22000"),
                total_risk=Decimal("100"), long_exposure=Decimal("22000"),
                short_exposure=Decimal("0"),
            ),
            correlation=None,
            margin=None,
            circuit_breaker=None,
            policy_version="1.0.0",
        )
        out = report_to_dict(report)
        assert out["decision"]["status"] == "RISK_APPROVED"
        assert out["account"]["currency"] == "USD"
        assert out["policy_version"] == "1.0.0"
