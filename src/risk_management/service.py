"""Central Risk Management Engine.

Orchestrates the full risk evaluation pipeline:

    Signal Validation
        -> Account & Instrument Info
        -> Stop-Loss Validation
        -> Position Sizing
        -> Take-Profit Validation
        -> Portfolio Exposure
        -> Daily Loss & Drawdown
        -> Margin & Spread
        -> Central Risk Decision
        -> Risk Report

Read-only and execution-independent. A RISK_APPROVED decision is hypothetical
and does NOT authorize any order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # avoid hard dependency on the news package
    from src.news.models import NewsRiskContext

from src.market_data.models import DataSource, InstrumentSpec
from src.risk_management.base import (
    AccountSnapshot,
    CircuitBreakerState,
    MarginSnapshot,
    PositionExposure,
    RiskDecision,
    RiskDecisionStatus,
    RiskEngineABC,
    RiskParameters,
    StopMethod,
)
from src.risk_management.config import (
    InstrumentGroup,
    RiskConfig,
    RiskPolicy,
    test_policy,
)
from src.risk_management.correlation import evaluate_correlation
from src.risk_management.circuit_breaker import CircuitBreaker
from src.risk_management.drawdown import DrawdownTracker
from src.risk_management.exposure import (
    ExposureInput,
    compute_position_exposure,
    aggregate_exposure,
)
from src.risk_management.margin import validate_margin, estimate_required_margin
from src.risk_management.models import (
    DailyPnLState,
    DrawdownState,
    ExposureSummary,
    RiskReport,
)
from src.risk_management.position_sizing import (
    PositionSizer,
    quote_to_account_rate,
    risk_amount_from_policy,
    round_down_to_step,
    stop_distance_from_params,
)
from src.risk_management.stop_loss import (
    StopLossResult,
    calculate_stop_price,
    check_stop_against_budget,
    derive_stop_distance,
    validate_stop_loss_price,
)
from src.risk_management.take_profit import (
    TakeProfitResult,
    calculate_tp_price,
    derive_target_distance,
    validate_take_profit_price,
)
from src.risk_management.validator import (
    validate_account,
    validate_instrument_spec,
    validate_policy,
    validate_signal_params,
)


@dataclass
class RiskEngine(RiskEngineABC):
    """Centralized risk management engine."""

    config: RiskConfig
    account: Optional[AccountSnapshot] = None
    instrument_specs: Dict[str, InstrumentSpec] = field(default_factory=dict)
    position_exposures: Dict[str, PositionExposure] = field(default_factory=dict)
    drawdown_tracker: Optional[DrawdownTracker] = None
    daily_pnl_state: Optional[DailyPnLState] = None
    circuit_breaker: Optional[CircuitBreaker] = None
    returns_history: Dict[str, list] = field(default_factory=dict)
    data_source: str = "mock"

    def __post_init__(self) -> None:
        if self.drawdown_tracker is None and self.config is not None:
            self.drawdown_tracker = DrawdownTracker(
                max_equity_drawdown_percent=self.config.policy.max_equity_drawdown_percent,
                max_balance_drawdown_percent=self.config.policy.max_balance_drawdown_percent,
            )
        if self.circuit_breaker is None:
            self.circuit_breaker = CircuitBreaker()
        if self.daily_pnl_state is None:
            self.daily_pnl_state = DailyPnLState(
                starting_balance=Decimal("0"),
                starting_equity=Decimal("0"),
            )
        if self.instrument_specs is None:
            self.instrument_specs = {}
        if self.position_exposures is None:
            self.position_exposures = {}
        if self.returns_history is None:
            self.returns_history = {}

    # ------------------------------------------------------------------
    # Policy
    # ------------------------------------------------------------------

    def validate_policy(self) -> List[str]:
        if self.config is None:
            return ["Risk configuration is not set"]
        return self.config.validate()

    def is_policy_valid(self) -> bool:
        return self.config is not None and self.config.is_valid

    def is_locked(self) -> bool:
        if self.circuit_breaker is None:
            return False
        return self.circuit_breaker.is_locked()

    # ------------------------------------------------------------------
    # Account / instrument provisioning
    # ------------------------------------------------------------------

    def set_account(self, account: AccountSnapshot) -> None:
        self.account = account

    def set_instrument_specs(self, specs: Dict[str, InstrumentSpec]) -> None:
        self.instrument_specs = dict(specs)

    def set_positions(self, positions: Dict[str, PositionExposure]) -> None:
        self.position_exposures = dict(positions)

    def set_returns_history(self, history: Dict[str, list]) -> None:
        self.returns_history = dict(history)

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def evaluate_signal(
        self,
        params: RiskParameters,
        account: AccountSnapshot,
        news_context: Optional["NewsRiskContext"] = None,
        now: Optional[datetime] = None,
    ) -> RiskDecision:
        """Evaluate a proposed trade signal through the full pipeline.

        Args:
            params: The proposed signal parameters.
            account: Account snapshot.
            news_context: Optional news/economic-calendar context. When provided,
                new entries may be blocked or flagged by the news gate. When
                ``None`` (default), no news gate applies — fully backward
                compatible with callers that do not use the news engine.
            now: Optional evaluation time. When provided (e.g. by the backtesting
                engine), staleness and daily-reset logic use this reference time
                instead of wall-clock time. Defaults to wall-clock now.
        """
        if now is None:
            now = datetime.now(timezone.utc)
        reasons: List[str] = []
        warnings: List[str] = []
        status = RiskDecisionStatus.APPROVED

        policy = self.config.policy if self.config else RiskPolicy()
        equity = account.equity
        balance = account.balance

        # --- 0. Circuit breaker ---
        if self.is_locked():
            cb = self.circuit_breaker.state if self.circuit_breaker else None
            return RiskDecision(
                signal_id=params.signal_id,
                symbol=params.symbol,
                instrument_type=params.instrument_type,
                direction=params.direction,
                status=RiskDecisionStatus.LOCKED,
                rejection_reasons=[
                    f"Account locked by circuit breaker: {cb.reason.value if cb and cb.reason else 'unknown'}"
                ],
                account_timestamp=account.timestamp,
                policy_version=self.config.policy.version if self.config else None,
                data_source=self.data_source,
            )

        # --- 0.5 News / economic-calendar gate (optional) ---
        if news_context is not None:
            if news_context.blocks_new_entries:
                reason = news_context.restriction_reason or "News window restriction"
                return RiskDecision(
                    signal_id=params.signal_id,
                    symbol=params.symbol,
                    instrument_type=params.instrument_type,
                    direction=params.direction,
                    status=RiskDecisionStatus.REJECTED,
                    rejection_reasons=[
                        f"New entry blocked by news window: {reason}"
                    ],
                    account_timestamp=account.timestamp,
                    policy_version=self.config.policy.version if self.config else None,
                    data_source=self.data_source,
                )
            if news_context.is_caution:
                warnings.append(
                    news_context.restriction_reason
                    or "Approaching news event window (caution)"
                )
        sig_val = validate_signal_params(params)
        if not sig_val.valid:
            reasons.extend(sig_val.reasons)
            status = sig_val.status
            return self._build_decision(
                params, account, status, reasons, warnings,
                None, None, None, None, None, None, None, None, None, None,
            )

        # --- 2. Account & instrument info ---
        acc_val = validate_account(
            account, max_staleness_seconds=policy.cooldown_minutes * 60,
            reference_time=now,
        )
        if not acc_val.valid:
            reasons.extend(acc_val.reasons)
            status = RiskDecisionStatus.REQUIRES_INFORMATION if acc_val.missing_fields else RiskDecisionStatus.REJECTED
            return self._build_decision(
                params, account, status, reasons, warnings,
                None, None, None, None, None, None, None, None, None, None,
            )

        spec = self.instrument_specs.get(params.symbol)
        inst_val = validate_instrument_spec(params.symbol, spec)
        if not inst_val.valid:
            reasons.extend(inst_val.reasons)
            status = RiskDecisionStatus.REQUIRES_INFORMATION if inst_val.missing_fields else RiskDecisionStatus.REJECTED
            return self._build_decision(
                params, account, status, reasons, warnings,
                None, None, None, None, None, None, None, None, None, None,
            )

        # --- 3. Stop-loss validation ---
        stop_method = StopMethod(params.stop_method or policy.default_stop_method)
        stop_distance = derive_stop_distance(params, policy)
        stop_loss_price = None
        stop_method_name = stop_method.value
        if stop_distance is None:
            reasons.append("Stop distance could not be determined")
            status = RiskDecisionStatus.REQUIRES_INFORMATION
        else:
            sl_reasons = self._validate_stop_side_and_limits(
                params.reference_price, stop_distance, params.direction, policy
            )
            reasons.extend(sl_reasons)
            if sl_reasons:
                status = RiskDecisionStatus.REJECTED
            else:
                stop_loss_price = calculate_stop_price(
                    params.reference_price, stop_distance, params.direction
                )

        # --- 4. Position sizing ---
        sizer = PositionSizer(
            spec=spec,
            account_currency=account.currency,
            rates=params.rates,
        )
        sizing = sizer.size(params, policy, equity, balance)
        volume = sizing.volume
        monetary_risk = sizing.monetary_risk
        risk_percent = sizing.risk_percent
        reasons.extend(sizing.reasons)
        warnings.extend(sizing.warnings)
        if sizing.reasons:
            status = RiskDecisionStatus.REJECTED

        volume_decimal = volume
        if volume is not None:
            volume_decimal = volume

        # --- 5. Take-profit validation ---
        tp_price = params.take_profit_price
        tp_distance = None
        rr = None
        tp_method_name = None
        if stop_distance is not None and stop_distance > 0:
            derived_tp = derive_target_distance(params, stop_distance, policy)
            if derived_tp is not None:
                tp_price = calculate_tp_price(
                    params.reference_price, derived_tp, params.direction
                )
                tp_distance = derived_tp
                _tp_method = params.tp_method or policy.default_tp_method
                tp_method_name = (
                    _tp_method.value if hasattr(_tp_method, "value") else str(_tp_method)
                )
            elif params.take_profit_price is not None:
                tp_distance = abs(params.take_profit_price - params.reference_price)
        else:
            if params.take_profit_price is not None:
                tp_distance = abs(params.take_profit_price - params.reference_price)

        if tp_price is not None and tp_distance is not None and stop_distance is not None and stop_distance > 0:
            tp_val = validate_take_profit_price(
                params.reference_price, stop_distance, tp_price, params.direction, policy
            )
            reasons.extend(tp_val.reasons)
            warnings.extend(tp_val.warnings)
            rr = tp_val.reward_to_risk
            tp_method_name = tp_val.method
            if tp_val.reasons:
                status = RiskDecisionStatus.REJECTED

        # --- 6. Portfolio exposure ---
        exposure_summary = self._build_exposure_summary(equity)
        proposed_notional = Decimal("0")
        if volume is not None and spec.contract_size:
            rate = quote_to_account_rate(
                spec.quote_currency or account.currency, account.currency,
                getattr(params, "_rates", {}) or {},
            ) or Decimal("1")
            proposed_notional = volume * params.reference_price * spec.contract_size * rate

        port_risk = self._evaluate_portfolio_risk(
            exposure_summary, volume, proposed_notional,
            params.direction, params.symbol, spec.instrument_type.value,
            equity, policy,
        )
        reasons.extend(port_risk.reasons)
        warnings.extend(port_risk.warnings)
        if not port_risk.within_limits:
            status = RiskDecisionStatus.REJECTED

        # --- 7. Daily loss & drawdown ---
        daily_result = self._evaluate_daily_loss(
            account, monetary_risk, policy, equity
        )
        reasons.extend(daily_result["reasons"])
        warnings.extend(daily_result["warnings"])
        if daily_result["breach"]:
            status = RiskDecisionStatus.REJECTED

        dd_result = self._evaluate_drawdown(account, policy)
        reasons.extend(dd_result["reasons"])
        warnings.extend(dd_result["warnings"])
        if dd_result["breach"]:
            status = RiskDecisionStatus.REJECTED

        # --- 8. Margin & spread ---
        margin_result = self._evaluate_margin(
            volume, params.reference_price, spec, account, policy
        )
        reasons.extend(margin_result["reasons"])
        warnings.extend(margin_result["warnings"])
        estimated_margin = margin_result["estimated_margin"]
        if not margin_result["sufficient"]:
            status = RiskDecisionStatus.REJECTED

        # Spread check
        spread_reasons = self._check_spread(params, policy)
        reasons.extend(spread_reasons)
        if spread_reasons:
            status = RiskDecisionStatus.REJECTED

        # --- Final status ---
        if reasons and status == RiskDecisionStatus.APPROVED:
            status = RiskDecisionStatus.REJECTED

        return self._build_decision(
            params, account, status, reasons, warnings,
            volume=volume_decimal,
            monetary_risk=monetary_risk,
            risk_percent=risk_percent,
            stop_loss_price=stop_loss_price,
            stop_distance=stop_distance,
            take_profit_price=tp_price,
            target_distance=tp_distance,
            reward_to_risk=rr,
            estimated_margin=estimated_margin,
            exposure_before=exposure_summary.by_instrument.get(params.symbol),
            exposure_after=None,
            stop_method=stop_method_name,
            tp_method=tp_method_name,
            sizing_method=policy.sizing_method.value,
        )

    # ------------------------------------------------------------------
    # Pipeline sub-steps
    # ------------------------------------------------------------------

    def _validate_stop_side_and_limits(
        self,
        entry: Decimal,
        distance: Decimal,
        direction: str,
        policy: RiskPolicy,
    ) -> List[str]:
        from src.risk_management.stop_loss import _validate_distance_limits, _validate_side
        reasons = _validate_side(entry, entry - distance if direction == "LONG" else entry + distance, direction)
        reasons.extend(_validate_distance_limits(distance, entry, policy))
        return reasons

    def _build_exposure_summary(self, equity: Decimal) -> ExposureSummary:
        positions = list(self.position_exposures.values())
        return aggregate_exposure(
            [self._exposure_to_position(p) for p in positions],
        )

    def _exposure_to_position(self, p: PositionExposure):
        # Minimal Position-like object for aggregate_exposure
        from types import SimpleNamespace
        from src.models import OrderSide
        side = OrderSide.LONG if p.direction == "LONG" else OrderSide.SHORT
        return SimpleNamespace(
            symbol=p.symbol,
            instrument_type=p.instrument_type,
            direction=side,
            volume=p.volume,
            open_price=p.open_price,
        )

    def _evaluate_portfolio_risk(
        self,
        summary: ExposureSummary,
        volume: Optional[Decimal],
        proposed_notional: Decimal,
        direction: str,
        symbol: str,
        asset_class: str,
        equity: Decimal,
        policy: RiskPolicy,
    ):
        from src.risk_management.portfolio_risk import evaluate_portfolio_risk
        return evaluate_portfolio_risk(
            summary=summary,
            proposed_volume=volume or Decimal("0"),
            proposed_notional=proposed_notional,
            proposed_direction=direction,
            proposed_symbol=symbol,
            proposed_asset_class=asset_class,
            equity=equity,
            policy=policy,
        )

    def _evaluate_daily_loss(
        self,
        account: AccountSnapshot,
        monetary_risk: Optional[Decimal],
        policy: RiskPolicy,
        equity: Decimal,
    ) -> Dict[str, Any]:
        reasons: List[str] = []
        warnings: List[str] = []
        breach = False

        if self.daily_pnl_state is None:
            self.daily_pnl_state = DailyPnLState(
                starting_balance=account.balance,
                starting_equity=account.equity,
            )

        d = self.daily_pnl_state
        limit_amount = equity * policy.max_daily_loss_percent
        if policy.max_daily_loss_amount is not None:
            limit_amount = min(limit_amount, policy.max_daily_loss_amount)

        daily_loss = abs(min(d.net_daily_pnl, Decimal("0")))
        if daily_loss >= limit_amount and limit_amount > 0:
            breach = True
            reasons.append(
                f"Daily loss limit reached: {daily_loss} >= {limit_amount}"
            )

        # Proposed trade risk vs remaining daily budget
        remaining = limit_amount - daily_loss
        if monetary_risk is not None and monetary_risk > remaining and remaining > 0:
            breach = True
            reasons.append(
                f"Proposed risk {monetary_risk} exceeds remaining daily budget {remaining}"
            )

        return {"reasons": reasons, "warnings": warnings, "breach": breach}

    def _evaluate_drawdown(
        self,
        account: AccountSnapshot,
        policy: RiskPolicy,
    ) -> Dict[str, Any]:
        reasons: List[str] = []
        warnings: List[str] = []
        breach = False

        if self.drawdown_tracker is not None:
            result = self.drawdown_tracker.update(account.equity, account.balance)
            if not result.within_equity_limit:
                breach = True
                reasons.extend(result.limit_breach_reasons)
            if not result.within_balance_limit:
                breach = True
                reasons.extend(result.limit_breach_reasons)

        return {"reasons": reasons, "warnings": warnings, "breach": breach}

    def _evaluate_margin(
        self,
        volume: Optional[Decimal],
        price: Optional[Decimal],
        spec: Optional[InstrumentSpec],
        account: AccountSnapshot,
        policy: RiskPolicy,
    ) -> Dict[str, Any]:
        reasons: List[str] = []
        warnings: List[str] = []
        estimated_margin = None
        sufficient = True

        if volume is not None and price is not None:
            contract_size = spec.contract_size if spec else None
            rate = Decimal("1")
            if spec and spec.quote_currency:
                rate = quote_to_account_rate(
                    spec.quote_currency, account.currency, {}
                ) or Decimal("1")
            estimated_margin = estimate_required_margin(
                volume, price, contract_size, account_leverage(account), rate
            )
            mr = validate_margin(
                volume=volume,
                price=price,
                contract_size=contract_size,
                account_equity=account.equity,
                account_free_margin=account.free_margin,
                account_margin_used=account.margin,
                leverage=account_leverage(account),
                conversion_rate=rate,
                policy=policy,
            )
            reasons.extend(mr.reasons)
            warnings.extend(mr.warnings)
            sufficient = mr.sufficient

        return {
            "reasons": reasons,
            "warnings": warnings,
            "estimated_margin": estimated_margin,
            "sufficient": sufficient,
        }

    def _check_spread(self, params: RiskParameters, policy: RiskPolicy) -> List[str]:
        reasons: List[str] = []
        if policy.max_spread_pips is not None and params.spread is not None:
            # Convert price spread to pips using tick/pip size heuristics
            if params.spread > policy.max_spread_pips:
                reasons.append(
                    f"Spread {params.spread} exceeds maximum {policy.max_spread_pips}"
                )
        return reasons

    # ------------------------------------------------------------------
    # Decision builder
    # ------------------------------------------------------------------

    def _build_decision(
        self,
        params: RiskParameters,
        account: AccountSnapshot,
        status: RiskDecisionStatus,
        reasons: List[str],
        warnings: List[str],
        volume: Optional[Decimal],
        monetary_risk: Optional[Decimal],
        risk_percent: Optional[Decimal],
        stop_loss_price: Optional[Decimal],
        stop_distance: Optional[Decimal],
        take_profit_price: Optional[Decimal],
        target_distance: Optional[Decimal],
        reward_to_risk: Optional[Decimal],
        estimated_margin: Optional[Decimal],
        exposure_before: Optional[PositionExposure],
        exposure_after: Optional[PositionExposure] = None,
        stop_method: Optional[str] = None,
        tp_method: Optional[str] = None,
        sizing_method: Optional[str] = None,
    ) -> RiskDecision:
        return RiskDecision(
            signal_id=params.signal_id,
            symbol=params.symbol,
            instrument_type=params.instrument_type,
            direction=params.direction,
            status=status,
            rejection_reasons=reasons,
            warnings=warnings,
            volume=volume,
            monetary_risk=monetary_risk,
            risk_percent=risk_percent,
            stop_loss_price=stop_loss_price,
            stop_distance=stop_distance,
            take_profit_price=take_profit_price,
            reward_to_risk=reward_to_risk,
            estimated_margin=estimated_margin,
            exposure_before=exposure_before,
            exposure_after=exposure_after,
            account_timestamp=account.timestamp,
            policy_version=self.config.policy.version if self.config else None,
            calculation_timestamp=datetime.now(timezone.utc),
            data_source=self.data_source,
            sizing_method=sizing_method,
            stop_method=stop_method,
            tp_method=tp_method,
        )

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def build_report(self, decision: RiskDecision) -> RiskReport:
        account = self.account or AccountSnapshot(
            login=0, name="unknown", server="", currency="USD",
            balance=Decimal("0"), equity=Decimal("0"),
            margin=Decimal("0"), free_margin=Decimal("0"),
        )
        return RiskReport(
            decision=decision,
            account_snapshot=account,
            drawdown_state=self.drawdown_tracker.state if self.drawdown_tracker else DrawdownState(
                equity_high_watermark=Decimal("0"),
                balance_high_watermark=Decimal("0"),
            ),
            daily_pnl_state=self.daily_pnl_state or DailyPnLState(
                starting_balance=Decimal("0"), starting_equity=Decimal("0")
            ),
            exposure_summary=self._build_exposure_summary(account.equity),
            correlation=evaluate_correlation(
                decision.symbol,
                list(self.position_exposures.keys()),
                self.returns_history,
                self.config.policy if self.config else RiskPolicy(),
            ),
            margin=MarginSnapshot(
                required_margin=decision.estimated_margin or Decimal("0"),
                available_margin=account.free_margin,
                free_margin=account.free_margin,
                margin_usage_percent=Decimal("0"),
                sufficient=decision.estimated_margin is None or decision.estimated_margin <= account.free_margin,
            ),
            circuit_breaker=self.circuit_breaker.state if self.circuit_breaker else CircuitBreakerState(),
            policy_version=self.config.policy.version if self.config else None,
        )


def account_leverage(account: AccountSnapshot) -> Optional[Decimal]:
    return account.leverage
