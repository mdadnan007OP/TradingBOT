"""Phase 9 order construction.

Builds an OrderRequest from a validated signal + risk decision + broker
instrument specification. Normalizes prices using actual tick size and price
precision, and volumes using actual volume step. Never rounds volume upward.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from src.models import OrderRequest, OrderSide, OrderType


@dataclass
class OrderBuildResult:
    request: OrderRequest
    normalized_entry_price: Decimal
    normalized_stop_loss: Optional[Decimal]
    normalized_take_profit: Optional[Decimal]
    normalized_volume: Decimal
    warnings: list = None


class OrderBuilder:
    """Constructs and normalizes broker order requests."""

    def __init__(self, magic_number: int, comment_prefix: str = "bot") -> None:
        self.magic_number = magic_number
        self.comment_prefix = comment_prefix

    def build_market_order(
        self,
        *,
        symbol: str,
        side: str,  # "LONG" | "SHORT"
        volume: Decimal,
        entry_reference_price: Decimal,
        stop_loss_price: Optional[Decimal],
        take_profit_price: Optional[Decimal],
        tick_bid: Decimal,
        tick_ask: Decimal,
        price_precision: int,
        tick_size: Decimal,
        lot_step: Decimal,
        min_lot: Decimal,
        max_lot: Decimal,
        stop_level: Decimal = Decimal("0"),
        deviation_points: int = 0,
    ) -> OrderBuildResult:
        warnings = []

        # Side-aware entry price: LONG uses ASK, SHORT uses BID.
        side_upper = side.upper()
        if side_upper == "LONG":
            entry_price = tick_ask
        elif side_upper == "SHORT":
            entry_price = tick_bid
        else:
            raise ValueError(f"Invalid side: {side}")

        # Normalize entry price to price precision / tick size.
        entry_price = self._normalize_price(entry_price, price_precision, tick_size)

        # Normalize SL/TP.
        sl = self._normalize_price(stop_loss_price, price_precision, tick_size) if stop_loss_price is not None else None
        tp = self._normalize_price(take_profit_price, price_precision, tick_size) if take_profit_price is not None else None

        # Validate stop distances (side-aware).
        if sl is not None:
            if side_upper == "LONG" and sl >= entry_price:
                warnings.append("LONG stop-loss at/above entry; adjusted not possible")
            if side_upper == "SHORT" and sl <= entry_price:
                warnings.append("SHORT stop-loss at/below entry")
            if stop_level > 0 and abs(entry_price - sl) < stop_level:
                warnings.append("Stop-loss distance below broker stop level")
        if tp is not None:
            if side_upper == "LONG" and tp <= entry_price:
                warnings.append("LONG take-profit at/below entry")
            if side_upper == "SHORT" and tp >= entry_price:
                warnings.append("SHORT take-profit at/above entry")

        # Normalize volume: round DOWN to lot step, never up.
        norm_volume = self._round_down_to_step(volume, lot_step)
        if norm_volume < min_lot:
            warnings.append(f"Volume {norm_volume} below min lot {min_lot}")
        if norm_volume > max_lot:
            warnings.append(f"Volume {norm_volume} above max lot {max_lot}")
        if norm_volume <= 0:
            norm_volume = Decimal("0")

        order_side = OrderSide.BUY if side_upper == "LONG" else OrderSide.SELL
        request = OrderRequest(
            symbol=symbol,
            side=order_side,
            order_type=OrderType.MARKET,
            volume=norm_volume,
            price=entry_price,
            stop_loss=sl,
            take_profit=tp,
            comment=f"{self.comment_prefix} magic={self.magic_number}",
            magic_number=self.magic_number,
        )

        return OrderBuildResult(
            request=request,
            normalized_entry_price=entry_price,
            normalized_stop_loss=sl,
            normalized_take_profit=tp,
            normalized_volume=norm_volume,
            warnings=warnings or [],
        )

    @staticmethod
    def _normalize_price(price: Decimal, precision: int, tick_size: Decimal) -> Decimal:
        # Round to nearest tick, then to price precision.
        if tick_size > 0:
            steps = (price / tick_size).quantize(Decimal("1"))
            price = steps * tick_size
        quant = Decimal(1).scaleb(-precision)  # 10^-precision
        return price.quantize(quant)

    @staticmethod
    def _round_down_to_step(volume: Decimal, step: Decimal) -> Decimal:
        if step <= 0:
            return volume
        steps = (volume / step).to_integral_value(rounding="ROUND_DOWN")
        return steps * step


def build_comment(strategy_name: str, magic_number: int, signal_id: str) -> str:
    short = signal_id[:8] if signal_id else "exec"
    return f"{strategy_name}#{magic_number} sig={short}"
