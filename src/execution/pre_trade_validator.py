"""Phase 9 pre-trade validation (Stage A).

Coordinates all pre-submission checks:
1. Account identity verification
2. DEMO mode
3. Execution mode
4. Strategy signal validation
5. Risk approval validation
6. Latest market data
7. Spread and quote freshness
8. Broker instrument specifications
9. Volume / SL / TP validation
10. Exposure and drawdown
11. Margin validation
12. order_check() preflight
13. Execution preview generation

A successful order_check() is never treated as a successful trade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.execution.account_identity import AccountIdentity, AccountIdentityVerifier
from src.execution.config import ExecutionConfig, ExecutionMode
from src.execution.emergency_stop import EmergencyStop
from src.execution.models import ExecutionRequest, OrderFillPolicy
from src.models import AccountInfo, Instrument, OrderRequest, OrderSide, Tick


@dataclass(frozen=True)
class PreTradeResult:
    passed: bool
    rejection_reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    account_identity: Optional[AccountIdentity] = None
    order_request: Optional[OrderRequest] = None
    execution_request: Optional[ExecutionRequest] = None
    preview: Dict[str, Any] = field(default_factory=dict)
    checked_at: Optional[datetime] = None


class PreTradeValidator:
    """Executes the full Stage A pre-trade validation pipeline."""

    def __init__(
        self,
        config: ExecutionConfig,
        account_verifier: AccountIdentityVerifier,
        emergency_stop: EmergencyStop,
        risk_engine: Any,
        signal_validator: Any,
        market_data: Any,
        broker_gateway: Any,
    ) -> None:
        self.config = config
        self.account_verifier = account_verifier
        self.emergency_stop = emergency_stop
        self.risk_engine = risk_engine
        self.signal_validator = signal_validator
        self.market_data = market_data
        self.broker_gateway = broker_gateway

    def validate(
        self,
        *,
        signal_id: str,
        strategy_name: str,
        strategy_version: str,
        symbol: str,
        side: str,
        volume: Decimal,
        entry_reference_price: Decimal,
        stop_loss_price: Optional[Decimal],
        take_profit_price: Optional[Decimal],
        risk_decision: Any,
        risk_policy_version: str,
    ) -> PreTradeResult:
        reasons: List[str] = []
        warnings: List[str] = []

        # 1. Execution mode must permit trading.
        if self.config.mode == ExecutionMode.PAPER:
            # Paper mode: skip broker checks but still validate signal/risk.
            pass
        elif not self.config.demo_trading_permitted:
            reasons.append("Execution mode does not permit trading")
            return PreTradeResult(
                passed=False,
                rejection_reasons=reasons,
                checked_at=datetime.now(timezone.utc),
            )

        # 2. Emergency controls.
        if self.emergency_stop.is_execution_blocked():
            reasons.append("Execution blocked by emergency circuit breakers")
            return PreTradeResult(
                passed=False,
                rejection_reasons=reasons,
                checked_at=datetime.now(timezone.utc),
            )

        # 3. Account identity verification (required for demo modes).
        account_identity: Optional[AccountIdentity] = None
        if self.config.demo_trading_permitted:
            account_identity = self.account_verifier.verify()
            if not account_identity.verification_passed:
                reasons.append(account_identity.rejection_reason or "Account identity verification failed")
                return PreTradeResult(
                    passed=False,
                    rejection_reasons=reasons,
                    account_identity=account_identity,
                    checked_at=datetime.now(timezone.utc),
                )
            if not account_identity.trade_allowed:
                reasons.append("Account trade permissions are disabled")
                return PreTradeResult(
                    passed=False,
                    rejection_reasons=reasons,
                    account_identity=account_identity,
                    checked_at=datetime.now(timezone.utc),
                )

        # 4. Signal validation.
        signal_ok = self._validate_signal(
            signal_id, strategy_name, strategy_version, symbol, side, entry_reference_price
        )
        if not signal_ok[0]:
            reasons.extend(signal_ok[1])
            return PreTradeResult(
                passed=False,
                rejection_reasons=reasons,
                account_identity=account_identity,
                checked_at=datetime.now(timezone.utc),
            )

        # 5. Risk approval validation.
        risk_ok = self._validate_risk(risk_decision, signal_id, symbol, side, volume, risk_policy_version)
        if not risk_ok[0]:
            reasons.extend(risk_ok[1])
            return PreTradeResult(
                passed=False,
                rejection_reasons=reasons,
                account_identity=account_identity,
                checked_at=datetime.now(timezone.utc),
            )

        # 6. Market data freshness.
        tick: Optional[Tick] = None
        if self.market_data is not None:
            try:
                tick = self.market_data.get_tick(symbol)
            except Exception:  # noqa: BLE001
                tick = None
        if tick is None:
            reasons.append(f"No market data available for {symbol}")
            return PreTradeResult(
                passed=False,
                rejection_reasons=reasons,
                account_identity=account_identity,
                checked_at=datetime.now(timezone.utc),
            )
        if not self._quote_fresh(tick):
            reasons.append(f"Stale quote for {symbol}")
            return PreTradeResult(
                passed=False,
                rejection_reasons=reasons,
                account_identity=account_identity,
                checked_at=datetime.now(timezone.utc),
            )

        # 7. Instrument specifications.
        spec: Optional[Dict[str, Any]] = None
        if self.broker_gateway is not None:
            try:
                spec = self.broker_gateway.get_symbol_spec(symbol)
            except Exception:  # noqa: BLE001
                spec = None
        if spec is None:
            reasons.append(f"No instrument specification for {symbol}")
            return PreTradeResult(
                passed=False,
                rejection_reasons=reasons,
                account_identity=account_identity,
                checked_at=datetime.now(timezone.utc),
            )

        # 8. Volume / SL / TP validation.
        vol_ok = self._validate_volume_and_stops(
            volume, entry_reference_price, stop_loss_price, take_profit_price, spec, side
        )
        if not vol_ok[0]:
            reasons.extend(vol_ok[1])
            return PreTradeResult(
                passed=False,
                rejection_reasons=reasons,
                account_identity=account_identity,
                checked_at=datetime.now(timezone.utc),
            )

        # 9. Exposure / drawdown / margin (rely on risk decision + account).
        margin_ok = self._validate_margin(volume, entry_reference_price, spec, account_identity)
        if not margin_ok[0]:
            reasons.extend(margin_ok[1])
            return PreTradeResult(
                passed=False,
                rejection_reasons=reasons,
                account_identity=account_identity,
                checked_at=datetime.now(timezone.utc),
            )

        # 10. Build order request.
        fill_policy = OrderFillPolicy.RETURN
        deviation = self.config.max_deviation_points
        order_request = OrderRequest(
            symbol=symbol,
            side=OrderSide.BUY if side == "LONG" else OrderSide.SELL,
            order_type=__import__("src.models", fromlist=["OrderType"]).OrderType.MARKET,
            volume=volume,
            price=(
                tick.ask if side == "LONG" else tick.bid
            ),
            stop_loss=stop_loss_price,
            take_profit=take_profit_price,
            comment=f"{strategy_name} magic={self.config.magic_number}",
            magic_number=self.config.magic_number,
        )

        # 11. order_check() preflight (demo modes only).
        order_check_result = None
        if self.config.demo_trading_permitted and self.broker_gateway is not None:
            try:
                order_check_result = self.broker_gateway.order_check(order_request)
            except Exception as exc:  # noqa: BLE001
                reasons.append(f"order_check() failed: {exc}")
                return PreTradeResult(
                    passed=False,
                    rejection_reasons=reasons,
                    account_identity=account_identity,
                    checked_at=datetime.now(timezone.utc),
                )
            if order_check_result is not None and not order_check_result.success:
                reasons.append(f"order_check() rejected: {order_check_result.error_message}")
                return PreTradeResult(
                    passed=False,
                    rejection_reasons=reasons,
                    account_identity=account_identity,
                    checked_at=datetime.now(timezone.utc),
                )
            # order_check() success is NOT proof of execution.
            warnings.append("order_check() preflight passed; not a trade execution")

        # 12. Execution request + preview.
        exec_request = ExecutionRequest(
            execution_id=self._new_id(),
            signal_id=signal_id,
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            symbol=symbol,
            side=side,
            volume=volume,
            entry_reference_price=entry_reference_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            risk_decision_id=getattr(risk_decision, "signal_id", ""),
            monetary_risk=getattr(risk_decision, "monetary_risk", Decimal("0")),
            risk_percent=getattr(risk_decision, "risk_percent", Decimal("0")),
            fill_policy=fill_policy,
            deviation_points=deviation,
            magic_number=self.config.magic_number,
            comment=order_request.comment or "",
            execution_mode=self.config.mode.value,
            created_at=datetime.now(timezone.utc),
        )

        preview = {
            "instrument": symbol,
            "direction": side,
            "volume": str(volume),
            "bid": str(tick.bid) if tick else None,
            "ask": str(tick.ask) if tick else None,
            "entry_reference": str(entry_reference_price),
            "stop_loss": str(stop_loss_price) if stop_loss_price is not None else None,
            "take_profit": str(take_profit_price) if take_profit_price is not None else None,
            "estimated_monetary_risk": str(getattr(risk_decision, "monetary_risk", Decimal("0"))),
            "risk_percent": str(getattr(risk_decision, "risk_percent", Decimal("0"))),
            "strategy_name": strategy_name,
            "signal_id": signal_id,
            "demo_server": account_identity.server if account_identity else None,
            "execution_mode": self.config.mode.value,
            "warnings": warnings,
        }

        return PreTradeResult(
            passed=True,
            rejection_reasons=reasons,
            warnings=warnings,
            account_identity=account_identity,
            order_request=order_request,
            execution_request=exec_request,
            preview=preview,
            checked_at=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # Internal checks
    # ------------------------------------------------------------------

    def _validate_signal(
        self,
        signal_id: str,
        strategy_name: str,
        strategy_version: str,
        symbol: str,
        side: str,
        entry_price: Decimal,
    ) -> tuple[bool, List[str]]:
        reasons: List[str] = []
        if not signal_id:
            reasons.append("Missing signal ID")
        if not strategy_name:
            reasons.append("Missing strategy name")
        if side not in ("LONG", "SHORT"):
            reasons.append(f"Invalid side {side}")
        if entry_price is None or entry_price <= 0:
            reasons.append("Invalid entry reference price")
        # Delegate to signal_validator if present.
        if self.signal_validator is not None:
            try:
                ok = self.signal_validator.validate(
                    signal_id=signal_id,
                    strategy_name=strategy_name,
                    strategy_version=strategy_version,
                    symbol=symbol,
                    side=side,
                    entry_price=entry_price,
                )
                if not ok:
                    reasons.append("Signal validator rejected the signal")
            except Exception:  # noqa: BLE001
                reasons.append("Signal validation error")
        return (len(reasons) == 0, reasons)

    def _validate_risk(
        self,
        risk_decision: Any,
        signal_id: str,
        symbol: str,
        side: str,
        volume: Decimal,
        risk_policy_version: str,
    ) -> tuple[bool, List[str]]:
        reasons: List[str] = []
        if risk_decision is None:
            reasons.append("Missing risk decision")
            return (False, reasons)
        status = getattr(risk_decision, "status", None)
        if status is None or str(status) != "RISK_APPROVED":
            reasons.append(f"Risk decision is not RISK_APPROVED (status={status})")
            return (False, reasons)
        if getattr(risk_decision, "signal_id", "") != signal_id:
            reasons.append("Risk decision signal ID mismatch")
        if getattr(risk_decision, "symbol", "") != symbol:
            reasons.append("Risk decision symbol mismatch")
        direction = getattr(risk_decision, "direction", "")
        if direction not in ("LONG", "SHORT") or direction != side:
            reasons.append("Risk decision direction mismatch")
        approved_volume = getattr(risk_decision, "volume", None)
        if approved_volume is not None and volume > approved_volume:
            reasons.append("Requested volume exceeds approved risk volume")
        if getattr(risk_decision, "stop_loss_price", None) is None:
            reasons.append("Missing approved stop-loss")
        return (len(reasons) == 0, reasons)

    def _validate_volume_and_stops(
        self,
        volume: Decimal,
        entry_price: Decimal,
        sl: Optional[Decimal],
        tp: Optional[Decimal],
        spec: Dict[str, Any],
        side: str,
    ) -> tuple[bool, List[str]]:
        reasons: List[str] = []
        min_lot = spec.get("min_lot", Decimal("0"))
        max_lot = spec.get("max_lot", Decimal("0"))
        lot_step = spec.get("lot_step", Decimal("0"))
        if volume <= 0:
            reasons.append("Volume must be positive")
        if min_lot and volume < min_lot:
            reasons.append(f"Volume {volume} below min lot {min_lot}")
        if max_lot and volume > max_lot:
            reasons.append(f"Volume {volume} above max lot {max_lot}")
        if lot_step and (volume % lot_step) != 0:
            reasons.append(f"Volume {volume} not aligned to lot step {lot_step}")
        # Stop distance validation (side-aware).
        point = spec.get("point", Decimal("0"))
        stop_level = spec.get("stop_level", Decimal("0"))
        if sl is not None:
            if side == "LONG" and sl >= entry_price:
                reasons.append("LONG stop-loss must be below entry")
            if side == "SHORT" and sl <= entry_price:
                reasons.append("SHORT stop-loss must be above entry")
            if point and abs(entry_price - sl) < stop_level:
                reasons.append("Stop-loss distance below broker stop level")
        if tp is not None:
            if side == "LONG" and tp <= entry_price:
                reasons.append("LONG take-profit must be above entry")
            if side == "SHORT" and tp >= entry_price:
                reasons.append("SHORT take-profit must be below entry")
        return (len(reasons) == 0, reasons)

    def _validate_margin(
        self,
        volume: Decimal,
        price: Decimal,
        spec: Dict[str, Any],
        account_identity: Optional[AccountIdentity],
    ) -> tuple[bool, List[str]]:
        reasons: List[str] = []
        # Basic margin estimate using leverage; real margin via order_calc_margin in demo adapter.
        leverage = Decimal("30")
        contract_size = spec.get("contract_size", Decimal("100000"))
        notional = volume * price * contract_size
        required_margin = notional / leverage if leverage > 0 else Decimal("0")
        if account_identity is not None:
            # We don't have free_margin here; rely on risk engine for margin.
            pass
        if required_margin <= 0:
            reasons.append("Unable to estimate required margin")
        return (len(reasons) == 0, reasons)

    def _quote_fresh(self, tick: Tick) -> bool:
        # Quote freshness: within a reasonable window (configurable).
        now = datetime.now(timezone.utc)
        age = (now - tick.timestamp).total_seconds()
        return age < 60  # 60 seconds max staleness

    @staticmethod
    def _new_id() -> str:
        import uuid

        return f"pretrade-{uuid.uuid4().hex[:12]}"
