"""Currency conversion for simulated PnL.

Converts profit-currency amounts into the account currency using static or
timestamp-appropriate (as-of) exchange rates. Future rates are never used in
historical simulations: when a historical rate series is supplied, only rates
with a timestamp <= the evaluation time are considered.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from datetime import datetime


class CurrencyConverter:
    """Converts amounts between profit currency and account currency."""

    def __init__(
        self,
        account_currency: str = "USD",
        static_rates: Optional[Dict[str, Decimal]] = None,
        historical_rates: Optional[Dict[str, List[Tuple[datetime, Decimal]]]] = None,
    ) -> None:
        self.account_currency = account_currency
        self.static_rates: Dict[str, Decimal] = dict(static_rates or {})
        # symbol/currency -> sorted list of (timestamp, rate)
        self.historical_rates: Dict[str, List[Tuple[datetime, Decimal]]] = {
            k: sorted(v, key=lambda t: t[0]) for k, v in (historical_rates or {}).items()
        }

    def rate(
        self,
        profit_currency: str,
        timestamp: Optional[datetime] = None,
    ) -> Optional[Decimal]:
        """Return units of account currency per 1 unit of ``profit_currency``.

        Returns None when no conversion is possible (caller must not invent one).
        """
        if profit_currency == self.account_currency:
            return Decimal("1")

        series = self.historical_rates.get(profit_currency)
        if series:
            if timestamp is None:
                return series[-1][1]
            chosen: Optional[Decimal] = None
            for ts, rate in series:
                if ts <= timestamp:
                    chosen = rate
                else:
                    break
            if chosen is not None and chosen > 0:
                return chosen
            # No as-of rate available; fall through to static only if present.

        static = self.static_rates.get(profit_currency)
        if static is not None and static > 0:
            return static
        return None

    def convert(
        self,
        amount_quote: Decimal,
        profit_currency: str,
        timestamp: Optional[datetime] = None,
    ) -> Optional[Decimal]:
        """Convert a profit-currency amount into the account currency."""
        rate = self.rate(profit_currency, timestamp)
        if rate is None:
            return None
        return amount_quote * rate

    def convert_or(
        self,
        amount_quote: Decimal,
        profit_currency: str,
        timestamp: Optional[datetime] = None,
        default: Optional[Decimal] = None,
    ) -> Decimal:
        """Convert, returning ``default`` (or 1:1) when conversion impossible."""
        result = self.convert(amount_quote, profit_currency, timestamp)
        if result is not None:
            return result
        if default is not None:
            return default
        # Last-resort 1:1 — caller should treat this as a documented limitation.
        return amount_quote