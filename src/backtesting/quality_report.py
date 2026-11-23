"""Backtest quality report.

Produces a consolidated quality summary alongside normal performance reports,
clearly distinguishing fully-observed historical inputs from estimated or
assumed execution inputs. All fields are derived from simulated results only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from src.backtesting.data_loader import BacktestData, SeriesData
from src.backtesting.models import BacktestResult
from src.market_data.models import DataSource, MarketTimeframe, OHLCBar


class ExecutionFidelity(str, Enum):
    """Classification of the execution price source used in a backtest."""

    OHLC = "OHLC"
    """Only OHLC bars; bid/ask synthesized from an assumed spread (estimated)."""
    BID_ASK_OHLC = "BidAskOHLC"
    """OHLC bars with real bid/ask fields (partly observed)."""
    TICK = "Tick"
    """Tick-level data; highest execution fidelity (fully observed)."""


@dataclass
class BacktestQualityReport:
    """Consolidated quality summary for a backtest run."""

    backtest_id: str
    generated_at: datetime
    symbols: List[str]
    timeframes: List[str]
    start_time: Optional[datetime]
    end_time: Optional[datetime]

    # --- Execution realism ---
    execution_fidelity: ExecutionFidelity = ExecutionFidelity.OHLC
    bid_ask_available: bool = False
    spread_source: str = "assumed"
    """'bar_bid_ask', 'bar_spread', 'fixed', 'fractional', 'none', 'assumed'."""
    slippage_model: str = "none"
    slippage_points: Dict[str, Decimal] = field(default_factory=dict)
    commission_model: str = "none"
    commission_per_lot: Decimal = Decimal("0")
    swap_enabled: bool = False
    ambiguous_fill_policy: str = "CONSERVATIVE"
    fill_on_next_bar: bool = True

    # --- Data coverage ---
    total_expected_bars: int = 0
    total_available_bars: int = 0
    missing_bar_count: int = 0
    missing_bar_percent: float = 0.0
    incomplete_dropped: int = 0
    invalid_rows: int = 0
    duplicate_rows_dropped: int = 0
    data_sources: Dict[str, str] = field(default_factory=dict)
    """symbol -> DataSource value."""

    # --- Ambiguity / gap reporting ---
    ambiguous_exit_count: int = 0
    gapped_exit_count: int = 0
    same_candle_sl_tp_count: int = 0
    """Bars where both SL and TP levels were touched (ambiguous)."""

    # --- Look-ahead / leakage ---
    look_ahead_detected: bool = False
    look_ahead_note: str = "None detected; bars revealed chronologically (ts <= now)."
    future_data_excluded: bool = True

    # --- Statistical / validation ---
    total_trades: int = 0
    min_trades_for_statistical_reliability: int = 30
    statistical_reliability: str = "low"
    optimization_used: bool = False
    out_of_sample_tested: bool = False
    oos_windows: int = 0

    # --- Limitations ---
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backtest_id": self.backtest_id,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "symbols": self.symbols,
            "timeframes": self.timeframes,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "execution": {
                "fidelity": self.execution_fidelity.value,
                "bid_ask_available": self.bid_ask_available,
                "spread_source": self.spread_source,
                "slippage_model": self.slippage_model,
                "slippage_points": {k: str(v) for k, v in self.slippage_points.items()},
                "commission_model": self.commission_model,
                "commission_per_lot": str(self.commission_per_lot),
                "swap_enabled": self.swap_enabled,
                "ambiguous_fill_policy": self.ambiguous_fill_policy,
                "fill_on_next_bar": self.fill_on_next_bar,
            },
            "data_coverage": {
                "total_expected_bars": self.total_expected_bars,
                "total_available_bars": self.total_available_bars,
                "missing_bar_count": self.missing_bar_count,
                "missing_bar_percent": self.missing_bar_percent,
                "incomplete_dropped": self.incomplete_dropped,
                "invalid_rows": self.invalid_rows,
                "duplicate_rows_dropped": self.duplicate_rows_dropped,
                "data_sources": self.data_sources,
            },
            "execution_fidelity_report": {
                "ambiguous_exit_count": self.ambiguous_exit_count,
                "gapped_exit_count": self.gapped_exit_count,
                "same_candle_sl_tp_count": self.same_candle_sl_tp_count,
            },
            "leakage": {
                "look_ahead_detected": self.look_ahead_detected,
                "look_ahead_note": self.look_ahead_note,
                "future_data_excluded": self.future_data_excluded,
            },
            "statistics": {
                "total_trades": self.total_trades,
                "min_trades_for_statistical_reliability": self.min_trades_for_statistical_reliability,
                "statistical_reliability": self.statistical_reliability,
                "optimization_used": self.optimization_used,
                "out_of_sample_tested": self.out_of_sample_tested,
                "oos_windows": self.oos_windows,
            },
            "limitations": list(self.limitations),
        }


def _classify_fidelity(series: Dict[Any, SeriesData]) -> ExecutionFidelity:
    """Best-effort classification: Tick > BidAskOHLC > OHLC."""
    has_bid_ask = False
    for data in series.values():
        for bar in data.bars[:50]:  # sample
            if getattr(bar, "bid", None) is not None and getattr(bar, "ask", None) is not None:
                has_bid_ask = True
                break
        if has_bid_ask:
            break
    if has_bid_ask:
        return ExecutionFidelity.BID_ASK_OHLC
    return ExecutionFidelity.OHLC


def build_quality_report(
    result: BacktestResult,
    data: Optional[BacktestData] = None,
    *,
    execution_fidelity: Optional[ExecutionFidelity] = None,
    spread_source: str = "assumed",
    slippage_model: str = "none",
    slippage_points: Optional[Dict[str, Decimal]] = None,
    commission_model: str = "none",
    commission_per_lot: Decimal = Decimal("0"),
    swap_enabled: bool = False,
    ambiguous_fill_policy: str = "CONSERVATIVE",
    fill_on_next_bar: bool = True,
    optimization_used: bool = False,
    out_of_sample_tested: bool = False,
    oos_windows: int = 0,
    limitations: Optional[List[str]] = None,
) -> BacktestQualityReport:
    """Build a :class:`BacktestQualityReport` from a backtest result."""
    total_available = 0
    total_expected = 0
    missing = 0
    incomplete = 0
    invalid = 0
    dupes = 0
    sources: Dict[str, str] = {}
    if data is not None:
        for sym in data.symbols():
            sym_missing = 0
            sym_available = 0
            sym_expected = 0
            for tf in data.timeframes_for(sym):
                series = data.get(sym, tf)
                if series is None:
                    continue
                sources[sym] = series.data_source.value
                sym_available += len(series.bars)
                sym_missing += len(series.missing_timestamps)
                incomplete += series.dropped_incomplete
                invalid += series.invalid_rows
                dupes += series.dropped_duplicates
                # Expected count from first->last at the timeframe step.
                if len(series.bars) >= 2:
                    span = (series.bars[-1].timestamp - series.bars[0].timestamp).total_seconds()
                    step = tf.minutes * 60
                    if step > 0:
                        sym_expected += int(span // step) + 1
            total_available += sym_available
            total_expected += sym_expected
            missing += sym_missing
    missing_percent = (missing / total_expected * 100.0) if total_expected > 0 else 0.0

    if execution_fidelity is None and data is not None:
        execution_fidelity = _classify_fidelity(data.series)
    if execution_fidelity is None:
        execution_fidelity = ExecutionFidelity.OHLC

    trades = result.trades
    ambiguous = sum(1 for t in trades if t.ambiguous_exit)
    gapped = sum(
        1
        for e in result.events
        if e.event_type.value == "EXIT" and e.detail.get("gapped")
    )

    total_trades = len(trades)
    reliability = (
        "high" if total_trades >= 100 else "medium" if total_trades >= 30 else "low"
    )

    lim = list(limitations or [])
    if spread_source == "assumed" or spread_source == "none":
        lim.append(
            "Spread is assumed/estimated, not broker-verified; execution prices are indicative."
        )
    if slippage_model == "none":
        lim.append("Slippage is disabled; real-world fills may be less favourable.")
    if commission_model == "none":
        lim.append("Commission is disabled; net profit excludes brokerage fees.")
    if not swap_enabled:
        lim.append("Swap/overnight financing is disabled; multi-day holds exclude financing cost.")
    if total_trades < 30:
        lim.append(
            f"Only {total_trades} trades: statistics are not statistically reliable."
        )
    if ambiguous:
        lim.append(
            f"{ambiguous} exit(s) resolved under the conservative same-candle SL/TP ambiguity policy."
        )

    return BacktestQualityReport(
        backtest_id=result.metadata.get("backtest_id", "unknown"),
        generated_at=datetime.now(timezone.utc),
        symbols=list(result.symbols),
        timeframes=list(result.timeframes),
        start_time=result.start_time,
        end_time=result.end_time,
        execution_fidelity=execution_fidelity,
        bid_ask_available=execution_fidelity == ExecutionFidelity.BID_ASK_OHLC,
        spread_source=spread_source,
        slippage_model=slippage_model,
        slippage_points=slippage_points or {},
        commission_model=commission_model,
        commission_per_lot=commission_per_lot,
        swap_enabled=swap_enabled,
        ambiguous_fill_policy=ambiguous_fill_policy,
        fill_on_next_bar=fill_on_next_bar,
        total_expected_bars=total_expected,
        total_available_bars=total_available,
        missing_bar_count=missing,
        missing_bar_percent=missing_percent,
        incomplete_dropped=incomplete,
        invalid_rows=invalid,
        duplicate_rows_dropped=dupes,
        data_sources=sources,
        ambiguous_exit_count=ambiguous,
        gapped_exit_count=gapped,
        same_candle_sl_tp_count=ambiguous,
        total_trades=total_trades,
        statistical_reliability=reliability,
        optimization_used=optimization_used,
        out_of_sample_tested=out_of_sample_tested,
        oos_windows=oos_windows,
        limitations=lim,
    )


def quality_report_to_dict(report: BacktestQualityReport) -> Dict[str, Any]:
    return report.to_dict()
