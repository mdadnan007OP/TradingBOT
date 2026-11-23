"""Execution simulator.

Decides simulated fills for entries and exits using only the price range of a
single historical bar. Applies spread (bid/ask), adverse slippage, gap handling
and a configurable, conservative same-candle stop/target ambiguity policy.

This module NEVER touches a broker. It only computes prices.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from src.backtesting.config import AmbiguousFillPolicy, ExecutionConfig
from src.backtesting.cost_model import TransactionCostModel
from src.backtesting.models import ExitReason, OrderSide, SimulatedPosition
from src.market_data.models import OHLCBar


@dataclass(frozen=True)
class FillResult:
    price: Decimal
    """Final fill price after slippage."""
    base_price: Decimal
    """Quote-side price before slippage (ask for buys, bid for sells)."""
    slippage: Decimal
    quote_side: str
    spread_source: str


@dataclass(frozen=True)
class ExitResult:
    price: Decimal
    """Final exit price after slippage."""
    raw_price: Decimal
    """Quote-side price before slippage."""
    slippage: Decimal
    reason: ExitReason
    ambiguous: bool = False
    gapped: bool = False
    fill: bool = True
    """False when the ambiguous-fill policy is SKIP (no fill this bar)."""


class ExecutionSimulator:
    """Computes simulated entries and stop/target exits."""

    def __init__(
        self,
        config: ExecutionConfig,
        costs: TransactionCostModel,
    ) -> None:
        self.config = config
        self.costs = costs

    # ------------------------------------------------------------------
    # Low-level fill
    # ------------------------------------------------------------------

    def _fill(self, symbol: str, is_buy: bool, ref_price: Decimal, bar: OHLCBar) -> FillResult:
        quote = self.costs.resolve_quote(symbol, ref_price, bar)
        base = quote.ask if is_buy else quote.bid
        price, slip = self.costs.fill_price(symbol, is_buy, base)
        return FillResult(
            price=price,
            base_price=base,
            slippage=slip,
            quote_side="ask" if is_buy else "bid",
            spread_source=quote.spread_source,
        )

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------

    def entry_fill(
        self,
        symbol: str,
        side: OrderSide,
        bar: OHLCBar,
        ref_price: Optional[Decimal] = None,
    ) -> FillResult:
        """Simulate a market entry.

        LONG entries buy at the ask; SHORT entries sell at the bid. Adverse
        slippage is applied on top. By default the reference is the bar open
        (next-bar entry); pass ``ref_price`` to override (e.g. bar close for
        same-bar fills).
        """
        is_buy = side == OrderSide.LONG
        ref = ref_price if ref_price is not None else bar.open
        return self._fill(symbol, is_buy, ref, bar)

    # ------------------------------------------------------------------
    # Exit (stop-loss / take-profit / manual)
    # ------------------------------------------------------------------

    @staticmethod
    def _long_sl_trigger(sl: Optional[Decimal], bar: OHLCBar) -> Optional[Decimal]:
        if sl is None:
            return None
        # Adverse gap: opened below the stop → fill at the open (worse).
        if bar.open < sl:
            return bar.open
        return sl

    @staticmethod
    def _long_tp_trigger(tp: Optional[Decimal], bar: OHLCBar) -> Optional[Decimal]:
        if tp is None:
            return None
        # Favourable gap: opened above the target → fill at the open (better).
        if bar.open > tp:
            return bar.open
        return tp

    @staticmethod
    def _short_sl_trigger(sl: Optional[Decimal], bar: OHLCBar) -> Optional[Decimal]:
        if sl is None:
            return None
        if bar.open > sl:
            return bar.open
        return sl

    @staticmethod
    def _short_tp_trigger(tp: Optional[Decimal], bar: OHLCBar) -> Optional[Decimal]:
        if tp is None:
            return None
        if bar.open < tp:
            return bar.open
        return tp

    def check_exit(self, position: SimulatedPosition, bar: OHLCBar) -> Optional[ExitResult]:
        """Return an ExitResult if the position's SL or TP is triggered in ``bar``."""
        sl = position.stop_loss_price
        tp = position.take_profit_price
        if sl is None and tp is None:
            return None

        if position.side == OrderSide.LONG:
            sl_hit = sl is not None and bar.low <= sl
            tp_hit = tp is not None and bar.high >= tp
            sl_trigger = self._long_sl_trigger(sl, bar)
            tp_trigger = self._long_tp_trigger(tp, bar)
            is_buy_close = False  # closing a long = sell
        else:
            sl_hit = sl is not None and bar.high >= sl
            tp_hit = tp is not None and bar.low <= tp
            sl_trigger = self._short_sl_trigger(sl, bar)
            tp_trigger = self._short_tp_trigger(tp, bar)
            is_buy_close = True  # closing a short = buy

        if not sl_hit and not tp_hit:
            return None

        ambiguous = sl_hit and tp_hit
        gapped = False

        if ambiguous:
            policy = self.config.ambiguous_fill_policy
            if policy == AmbiguousFillPolicy.SKIP:
                return ExitResult(
                    price=Decimal("0"),
                    raw_price=Decimal("0"),
                    slippage=Decimal("0"),
                    reason=ExitReason.STOP_LOSS,
                    ambiguous=True,
                    gapped=False,
                    fill=False,
                )
            if policy == AmbiguousFillPolicy.CONSERVATIVE:
                chosen_sl = True
            else:  # OPTIMISTIC (explicitly opted-in; not recommended)
                chosen_sl = False
        else:
            chosen_sl = sl_hit

        if chosen_sl:
            trigger = sl_trigger
            reason = ExitReason.STOP_LOSS
        else:
            trigger = tp_trigger
            reason = ExitReason.TAKE_PROFIT

        if trigger is None:
            return None

        # Gap detection: open beyond the intended stop/target level.
        level = sl if chosen_sl else tp
        if level is not None:
            if chosen_sl:
                gapped = (bar.open < level) if position.side == OrderSide.LONG else (bar.open > level)
            else:
                gapped = (bar.open > level) if position.side == OrderSide.LONG else (bar.open < level)

        fill = self._fill(position.symbol, is_buy_close, trigger, bar)
        return ExitResult(
            price=fill.price,
            raw_price=fill.base_price,
            slippage=fill.slippage,
            reason=reason,
            ambiguous=ambiguous,
            gapped=gapped,
            fill=True,
        )

    def manual_exit(self, symbol: str, side: OrderSide, ref_price: Decimal, bar: OHLCBar) -> ExitResult:
        """Simulate a manual (signal/end) exit at ``ref_price``."""
        is_buy_close = side == OrderSide.SHORT
        fill = self._fill(symbol, is_buy_close, ref_price, bar)
        return ExitResult(
            price=fill.price,
            raw_price=fill.base_price,
            slippage=fill.slippage,
            reason=ExitReason.MANUAL,
        )