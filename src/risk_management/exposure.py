"""Portfolio exposure computation.

Aggregates open positions into notional and directional exposure by symbol and
asset class. Does not modify positions.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional

from src.models import Position
from src.risk_management.models import ExposureSummary, PositionExposure


@dataclass(frozen=True)
class ExposureInput:
    symbol: str
    instrument_type: str
    direction: str  # LONG / SHORT
    volume: Decimal
    open_price: Decimal
    contract_size: Decimal = Decimal("1")
    conversion_rate: Decimal = Decimal("1")


def compute_position_exposure(
    symbol: str,
    instrument_type: str,
    direction: str,
    volume: Decimal,
    open_price: Decimal,
    contract_size: Decimal = Decimal("1"),
    conversion_rate: Decimal = Decimal("1"),
) -> PositionExposure:
    """Compute notional exposure (in account currency) for one position."""
    notional = volume * open_price * contract_size * conversion_rate
    return PositionExposure(
        symbol=symbol,
        instrument_type=instrument_type,
        direction=direction,
        volume=volume,
        open_price=open_price,
        notional=notional,
        asset_class=instrument_type,
    )


def aggregate_exposure(
    positions: List[Position],
    contract_sizes: Optional[Dict[str, Decimal]] = None,
    conversion_rates: Optional[Dict[str, Decimal]] = None,
) -> ExposureSummary:
    """Aggregate a list of positions into an exposure summary.

    contract_sizes: symbol -> contract size (default 1).
    conversion_rates: symbol -> rate from profit currency to account currency.
    """
    contract_sizes = contract_sizes or {}
    conversion_rates = conversion_rates or {}

    total_notional = Decimal("0")
    total_risk = Decimal("0")
    long_exposure = Decimal("0")
    short_exposure = Decimal("0")
    by_asset_class: Dict[str, Decimal] = {}
    # Mutable accumulator per symbol: [volume, notional, instrument_type, direction]
    acc: Dict[str, list] = {}

    for pos in positions:
        cs = contract_sizes.get(pos.symbol, Decimal("1"))
        rate = conversion_rates.get(pos.symbol, Decimal("1"))
        notional = pos.volume * pos.open_price * cs * rate
        total_notional += notional

        if pos.direction.value == "LONG":
            long_exposure += notional
        elif pos.direction.value == "SHORT":
            short_exposure += notional

        if pos.symbol not in acc:
            acc[pos.symbol] = [
                pos.volume,
                notional,
                pos.instrument_type,
                pos.direction.value,
            ]
        else:
            acc[pos.symbol][0] += pos.volume
            acc[pos.symbol][1] += notional

        ac = pos.instrument_type
        by_asset_class[ac] = by_asset_class.get(ac, Decimal("0")) + notional

    by_instrument: Dict[str, PositionExposure] = {}
    for symbol, (volume, notional, itype, direction) in acc.items():
        by_instrument[symbol] = PositionExposure(
            symbol=symbol,
            instrument_type=itype,
            direction=direction,
            volume=volume,
            open_price=Decimal("0"),
            notional=notional,
            asset_class=itype,
        )

    if long_exposure > short_exposure:
        bias = "long"
    elif short_exposure > long_exposure:
        bias = "short"
    else:
        bias = "neutral"

    return ExposureSummary(
        total_positions=len(positions),
        total_notional=total_notional,
        total_risk=total_risk,
        long_exposure=long_exposure,
        short_exposure=short_exposure,
        by_instrument=by_instrument,
        by_asset_class=by_asset_class,
        directional_bias=bias,
    )
