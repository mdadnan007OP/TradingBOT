"""Risk report generation and formatting.

Produces plain-dict and text representations of risk decisions and full
reports for logging, audit, and downstream consumption.
"""

from __future__ import annotations

from typing import Any, Dict

from src.risk_management.base import RiskDecision
from src.risk_management.models import RiskReport


def decision_to_dict(decision: RiskDecision) -> Dict[str, Any]:
    """Serialize a RiskDecision to a plain dict."""
    return {
        "signal_id": decision.signal_id,
        "symbol": decision.symbol,
        "instrument_type": decision.instrument_type,
        "direction": decision.direction,
        "status": decision.status.value,
        "rejection_reasons": decision.rejection_reasons,
        "warnings": decision.warnings,
        "volume": str(decision.volume) if decision.volume is not None else None,
        "monetary_risk": (
            str(decision.monetary_risk) if decision.monetary_risk is not None else None
        ),
        "risk_percent": (
            str(decision.risk_percent) if decision.risk_percent is not None else None
        ),
        "stop_loss_price": (
            str(decision.stop_loss_price) if decision.stop_loss_price is not None else None
        ),
        "take_profit_price": (
            str(decision.take_profit_price) if decision.take_profit_price is not None else None
        ),
        "reward_to_risk": (
            str(decision.reward_to_risk) if decision.reward_to_risk is not None else None
        ),
        "estimated_margin": (
            str(decision.estimated_margin) if decision.estimated_margin is not None else None
        ),
        "calculation_timestamp": decision.calculation_timestamp.isoformat(),
        "data_source": decision.data_source,
        "sizing_method": decision.sizing_method,
        "stop_method": decision.stop_method,
        "tp_method": decision.tp_method,
    }


def report_to_dict(report: RiskReport) -> Dict[str, Any]:
    """Serialize a full RiskReport to a plain dict."""
    return {
        "decision": decision_to_dict(report.decision),
        "account": {
            "login": report.account_snapshot.login,
            "name": report.account_snapshot.name,
            "currency": report.account_snapshot.currency,
            "balance": str(report.account_snapshot.balance),
            "equity": str(report.account_snapshot.equity),
            "free_margin": str(report.account_snapshot.free_margin),
            "trade_mode": report.account_snapshot.trade_mode,
            "timestamp": (
                report.account_snapshot.timestamp.isoformat()
                if report.account_snapshot.timestamp else None
            ),
        },
        "drawdown": {
            "equity_drawdown_percent": str(
                report.drawdown_state.compute_equity_drawdown(
                    report.account_snapshot.equity
                )
            ),
            "balance_drawdown_percent": str(
                report.drawdown_state.compute_balance_drawdown(
                    report.account_snapshot.balance
                )
            ),
            "equity_high_watermark": str(report.drawdown_state.equity_high_watermark),
            "balance_high_watermark": str(report.drawdown_state.balance_high_watermark),
            "max_equity_drawdown_ever": str(
                report.drawdown_state.max_equity_drawdown_ever
            ),
            "max_balance_drawdown_ever": str(
                report.drawdown_state.max_balance_drawdown_ever
            ),
        },
        "daily_pnl": {
            "net_daily_pnl": str(report.daily_pnl_state.net_daily_pnl),
            "net_daily_pnl_percent": str(
                report.daily_pnl_state.net_daily_pnl_percent
            ),
            "trading_locked": report.daily_pnl_state.trading_locked,
        },
        "exposure": {
            "total_positions": report.exposure_summary.total_positions,
            "total_notional": str(report.exposure_summary.total_notional),
            "directional_bias": report.exposure_summary.directional_bias,
        },
        "correlation": (
            {
                "candidate_symbol": report.correlation.candidate_symbol,
                "correlated_symbols": report.correlation.correlated_symbols,
                "max_correlation": (
                    str(report.correlation.max_correlation)
                    if report.correlation.max_correlation is not None
                    else None
                ),
                "breach": report.correlation.breach,
                "sufficient_data": report.correlation.sufficient_data,
            }
            if report.correlation is not None
            else None
        ),
        "margin": (
            {
                "required_margin": str(report.margin.required_margin),
                "available_margin": str(report.margin.available_margin),
                "sufficient": report.margin.sufficient,
            }
            if report.margin is not None
            else None
        ),
        "circuit_breaker": (
            {
                "active": report.circuit_breaker.active,
                "reason": (
                    report.circuit_breaker.reason.value
                    if report.circuit_breaker.reason else None
                ),
            }
            if report.circuit_breaker is not None
            else None
        ),
        "policy_version": report.policy_version,
        "generated_at": report.generated_at.isoformat(),
    }


def format_decision_text(decision: RiskDecision) -> str:
    """Human-readable single-line summary of a risk decision."""
    lines = [
        f"[{decision.status.value}] {decision.symbol} {decision.direction}",
        f"  signal_id={decision.signal_id}",
    ]
    if decision.volume is not None:
        lines.append(f"  volume={decision.volume}")
    if decision.monetary_risk is not None:
        lines.append(f"  monetary_risk={decision.monetary_risk}")
    if decision.risk_percent is not None:
        lines.append(f"  risk_percent={decision.risk_percent}%")
    if decision.stop_loss_price is not None:
        lines.append(f"  stop_loss={decision.stop_loss_price}")
    if decision.take_profit_price is not None:
        lines.append(f"  take_profit={decision.take_profit_price}")
    if decision.reward_to_risk is not None:
        lines.append(f"  reward_to_risk={decision.reward_to_risk}")
    if decision.rejection_reasons:
        lines.append("  rejection_reasons:")
        for r in decision.rejection_reasons:
            lines.append(f"    - {r}")
    if decision.warnings:
        lines.append("  warnings:")
        for w in decision.warnings:
            lines.append(f"    - {w}")
    return "\n".join(lines)
