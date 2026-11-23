"""Backtesting engine.

Event-driven historical simulation that REUSES the existing Phase 4 (indicators),
Phase 5 (strategies), Phase 6 (risk) and Phase 7 (news) engines. It never places
real or demo broker orders and never calls any MT5 execution function.

Pipeline per symbol bar (chronological, look-ahead-safe):

    1. Fill pending market entries at the bar open (from a prior bar's signal).
    2. Check stop-loss / take-profit against the bar range (gap-aware).
    3. Generate signals from the *revealed* candle window (<= now).
    4. Apply news restrictions (as-of) and the Phase 6 risk engine.
    5. Open a simulated position (immediately or as a pending next-bar order).
    6. Record an equity point.

Look-ahead prevention:
    * Only revealed candles (timestamp <= now) are passed to indicators/strategies.
    * Entries fill on the *next* bar (or at the signal bar close, configurable).
    * News uses as-of timestamps; risk state (drawdown/daily) is carried forward.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.backtesting.config import BacktestConfig
from src.backtesting.cost_model import TransactionCostModel
from src.backtesting.currency_conversion import CurrencyConverter
from src.backtesting.data_loader import BacktestData
from src.backtesting.event_loop import EventScheduler
from src.backtesting.execution_simulator import ExecutionSimulator
from src.backtesting.market_simulator import MarketSimulator
from src.backtesting.models import (
    BacktestEvent,
    BacktestResult,
    EventType,
    ExitReason,
    OrderSide,
    OrderType,
)
from src.backtesting.portfolio_simulator import PortfolioSimulator
from src.backtesting.quality_report import BacktestQualityReport
from src.indicators import create_engine
from src.market_data.models import DataSource, MarketTimeframe, spec_for_symbol
from src.risk_management.base import RiskParameters
from src.risk_management.config import RiskConfig, test_policy
from src.risk_management.models import DailyPnLState
from src.risk_management.service import RiskEngine
from src.strategies import create_strategy_manager
from src.strategies.base import Signal, SignalDirection
from src.strategies.models import StrategyParameters

logger = logging.getLogger(__name__)


class BacktestEngine:
    """Event-driven historical backtesting engine (simulation only)."""

    def __init__(
        self,
        config: BacktestConfig,
        data: BacktestData,
        risk_engine: Optional[RiskEngine] = None,
        news_service: Optional[Any] = None,
        indicator_engine: Optional[Any] = None,
        strategy_manager: Optional[Any] = None,
    ) -> None:
        self.config = config
        self.data = data

        self.indicator_engine = indicator_engine or create_engine()
        self.strategy_manager = strategy_manager or create_strategy_manager(self.indicator_engine)
        self._configure_strategies()

        self.converter = CurrencyConverter(
            account_currency=config.account.currency,
            static_rates=dict(config.currency_rates),
        )
        self.costs = TransactionCostModel(config.execution, self.converter)
        self.execution = ExecutionSimulator(config.execution, self.costs)

        specs = {}
        for symbol in data.symbols():
            spec = spec_for_symbol(symbol)
            if spec is not None:
                specs[symbol] = spec
        self.specs = specs

        self.portfolio = PortfolioSimulator(
            config.account, self.costs, self.execution, specs
        )
        self.market = MarketSimulator(data)
        self.scheduler = EventScheduler(data)

        self.risk_engine = risk_engine or self._build_risk_engine()
        self.news_service = news_service if config.news_enabled else None

        self._enabled: List[str] = list(self.strategy_manager.list_enabled())
        if config.strategies:
            self._enabled = [s for s in self._enabled if s in config.strategies]

        self._params_map: Dict[str, StrategyParameters] = {}
        for name in self._enabled:
            strategy = self.strategy_manager.registry.get(name)
            values = dict(strategy.default_parameters.values) if strategy else {}
            values.update(config.strategy_parameters.get(name, {}))
            # Disable wall-clock signal expiry in backtests: signal_valid_until is
            # None so historical signals are never dropped by real "now".
            self._params_map[name] = StrategyParameters(
                values=values,
                max_signal_age_minutes=None,
            )

        self.entry_tf: Dict[str, MarketTimeframe] = {
            symbol: self._pick_entry_timeframe(symbol) for symbol in data.symbols()
        }
        self._last_prices: Dict[str, Decimal] = {}
        self._order_risk: Dict[str, Decimal] = {}
        self._order_bar_index: Dict[str, int] = {}
        self._bar_index = 0
        self._current_day: Optional[object] = None
        self._day_start_balance: Decimal = config.account.starting_balance
        self._day_start_equity: Decimal = config.account.starting_balance
        self._day_start_unrealized: Decimal = Decimal("0")
        self.backtest_id: str = f"bt-{uuid.uuid4().hex[:12]}"
        self._ambiguous_exits: int = 0

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _configure_strategies(self) -> None:
        enabled = self.config.strategies
        if not enabled:
            return
        for name in self.strategy_manager.registry.supported_strategies():
            if name not in enabled:
                self.strategy_manager.disable_strategy(name)

    def _build_risk_engine(self) -> RiskEngine:
        policy = self.config.risk_policy or test_policy()
        rc = RiskConfig(policy=policy)
        rc = rc.validate_policy()
        engine = RiskEngine(config=rc)
        if self.specs:
            engine.set_instrument_specs(dict(self.specs))
        return engine

    def _pick_entry_timeframe(self, symbol: str) -> MarketTimeframe:
        tfs = self.data.timeframes_for(symbol)
        if not tfs:
            return MarketTimeframe.H1
        return sorted(tfs, key=lambda t: t.minutes)[0]

    def _instrument_type(self, symbol: str) -> str:
        spec = self.specs.get(symbol)
        return spec.instrument_type.value if spec else "forex"

    def _extract_atr(self, signal: Signal) -> Optional[Decimal]:
        for key, series in signal.indicator_snapshot.items():
            if "atr" in key.lower() and series:
                for value in reversed(series):
                    if value is not None:
                        return value
        return None

    def _fallback_stop_distance(self, symbol: str, ref_price: Decimal) -> Decimal:
        return ref_price * self.config.fallback_stop_fraction

    # ------------------------------------------------------------------
    # Risk parameters
    # ------------------------------------------------------------------

    def _build_risk_parameters(
        self,
        signal: Signal,
        symbol: str,
        bar,
        account,
    ) -> RiskParameters:
        policy = self.risk_engine.config.policy
        direction = signal.direction.value
        ref = signal.reference_price or bar.close
        tech = signal.technical_invalidation
        atr_val = self._extract_atr(signal)

        if tech is not None:
            stop_method = "technical_invalidation"
            stop_distance = None
        elif atr_val is not None:
            stop_method = "atr_based"
            stop_distance = None
        else:
            stop_method = "fixed_distance"
            stop_distance = self._fallback_stop_distance(symbol, ref)

        try:
            spread = self.costs.resolve_quote(symbol, bar.close, bar).spread
        except Exception:
            spread = None

        return RiskParameters(
            signal_id=signal.signal_id,
            symbol=symbol,
            instrument_type=self._instrument_type(symbol),
            direction=direction,
            reference_price=ref,
            technical_invalidation=tech,
            stop_loss_price=None,
            take_profit_price=None,
            stop_distance=stop_distance,
            atr_value=atr_val,
            atr_multiplier=policy.atr_multiplier,
            reward_to_risk=policy.default_reward_to_risk,
            swing_high=None,
            swing_low=None,
            account_currency=account.currency,
            equity=account.equity,
            balance=account.balance,
            free_margin=account.free_margin,
            margin=account.margin,
            leverage=account.leverage,
            spread=spread,
            slippage_estimate=None,
            stop_method=stop_method,
            tp_method="reward_to_risk",
            rates=dict(self.config.currency_rates),
        )

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(self) -> BacktestResult:
        result = BacktestResult(
            config_name=self.config.name,
            symbols=list(self.data.symbols()),
            timeframes=[tf.value for tf in self.data.timeframes()],
            start_time=self.data.global_start(),
            end_time=self.data.global_end(),
        )
        result.metadata["config"] = self.config.to_dict()
        result.metadata["strategies"] = list(self._enabled)
        result.metadata["backtest_id"] = self.backtest_id
        result.metadata["data_source"] = "historical"
        result.metadata["execution_model"] = "ohlc_next_bar_fill"
        result.metadata["look_ahead"] = "none"
        result.metadata["ambiguous_fill_policy"] = self.config.execution.ambiguous_fill_policy.value
        try:
            import importlib.metadata as _md
            result.metadata["python_version"] = __import__("sys").version
            result.metadata["backtesting_version"] = "0.3.0-phase8"
        except Exception:
            pass

        for ts in self.scheduler.timestamps():
            self.market.reveal_through(ts)
            for event in self.scheduler.bars_at(ts):
                self._last_prices[event.symbol] = event.bar.close
                if event.timeframe == self.entry_tf.get(event.symbol):
                    self._process_symbol_bar(event.symbol, event.bar, ts, result)
            self._update_risk_state(ts)
            self.portfolio.record_equity_point(ts, dict(self._last_prices))

        # Close any remaining positions at the final prices.
        if self.portfolio.open_positions:
            end_time = self.data.global_end() or datetime.now(timezone.utc)
            self.portfolio.close_all(
                dict(self._last_prices), end_time, reason=ExitReason.END_OF_DATA
            )
            self.portfolio.record_equity_point(end_time, dict(self._last_prices))

        result.equity_curve = list(self.portfolio.equity_curve)
        result.trades = list(self.portfolio.closed_trades)
        result.rejected_signals.extend(self._collect_rejections())
        result.metadata["ambiguous_exits"] = self._ambiguous_exits
        result.metadata["total_events"] = len(result.events)
        if self.news_service is not None:
            result.warnings.append(
                "Historical news coverage may be incomplete; news restrictions use "
                "only as-of data available at each simulated timestamp."
            )
        if self.config.execution.swap.enabled:
            result.warnings.append(
                "Swap/financing uses configured test assumptions, not broker-verified rates."
            )
        if self.config.execution.commission.model.value == "none":
            result.warnings.append("Commission is disabled; results exclude brokerage fees.")
        return result

    # ------------------------------------------------------------------
    # Per-bar processing
    # ------------------------------------------------------------------

    def _process_symbol_bar(self, symbol: str, bar, ts: datetime, result: BacktestResult) -> None:
        self._bar_index += 1
        # 1. Fill pending entries at bar open.
        self._fill_pending(symbol, bar, ts, result)
        # 2. Stop-loss / take-profit.
        closed = self.portfolio.check_exits(symbol, bar)
        for trade in closed:
            if trade.ambiguous_exit:
                self._ambiguous_exits += 1
            result.events.append(BacktestEvent(
                EventType.EXIT, trade.exit_time, symbol,
                {"trade_id": trade.trade_id, "reason": trade.exit_reason.value,
                 "net_pnl": str(trade.net_pnl_account), "ambiguous": trade.ambiguous_exit},
            ))
        # 3. Generate signals from revealed candles.
        candles_by_tf = {
            tf: self.market.window(symbol, tf)
            for tf in self.data.timeframes_for(symbol)
        }
        candles_by_tf = {tf: c for tf, c in candles_by_tf.items() if c}

        for name in self._enabled:
            params = self._params_map.get(name)
            try:
                sres = self.strategy_manager.run_strategy(
                    name, symbol, candles_by_tf,
                    parameters=params, data_source=DataSource.HISTORICAL,
                )
            except Exception as exc:  # noqa: BLE001 - fault isolation
                logger.debug("Strategy %s error on %s: %s", name, symbol, exc)
                continue
            for sig in sres.active_signals:
                self._handle_signal(sig, symbol, bar, ts, result)
            for rej in sres.rejections:
                result.rejected_signals.append({
                    "strategy": rej.strategy_name,
                    "symbol": rej.symbol,
                    "category": rej.category,
                    "reason": rej.reason,
                    "timestamp": rej.timestamp.isoformat() if rej.timestamp else None,
                })

    def _fill_pending(self, symbol: str, bar, ts: datetime, result: BacktestResult) -> None:
        for order in list(self.portfolio.order_sim.pending(symbol)):
            if order.order_type != OrderType.MARKET:
                continue
            fill = self.execution.entry_fill(symbol, order.side, bar)
            self.portfolio.order_sim.mark_filled(order.order_id, fill.price, ts)
            risk_amount = self._order_risk.get(order.order_id)
            pos = self.portfolio.open_position(
                symbol=symbol,
                side=order.side,
                volume=order.volume,
                fill_price=fill.price,
                fill_time=ts,
                stop_loss_price=order.stop_loss_price,
                take_profit_price=order.take_profit_price,
                strategy_name=order.strategy_name,
                signal_id=order.signal_id,
                risk_amount=risk_amount,
                entry_slippage_price=fill.slippage,
            )
            result.events.append(BacktestEvent(
                EventType.FILL, ts, symbol,
                {"order_id": order.order_id, "price": str(fill.price),
                 "slippage": str(fill.slippage), "opened": pos is not None},
            ))
            self._order_risk.pop(order.order_id, None)
            self._order_bar_index.pop(order.order_id, None)

    def _handle_signal(self, signal: Signal, symbol: str, bar, ts: datetime, result: BacktestResult) -> None:
        if signal.direction == SignalDirection.NONE:
            return
        if not signal.is_actionable(ts):
            return

        result.events.append(BacktestEvent(
            EventType.SIGNAL, ts, symbol,
            {"signal_id": signal.signal_id, "strategy": signal.strategy_name,
             "direction": signal.direction.value, "ref": str(signal.reference_price)},
        ))

        # News gate (as-of).
        news_ctx = None
        if self.news_service is not None:
            try:
                news_ctx = self.news_service.risk_context(symbol, now=ts)
            except Exception as exc:  # noqa: BLE001
                logger.debug("News context error for %s: %s", symbol, exc)
                news_ctx = None
            if news_ctx is not None and news_ctx.blocks_new_entries:
                result.news_blocks.append({
                    "symbol": symbol,
                    "timestamp": ts.isoformat(),
                    "reason": news_ctx.restriction_reason,
                    "window_status": news_ctx.window_status.value,
                })
                result.events.append(BacktestEvent(
                    EventType.NEWS_BLOCK, ts, symbol,
                    {"reason": news_ctx.restriction_reason},
                ))
                return

        account = self.portfolio.account_snapshot(dict(self._last_prices), ts)
        params = self._build_risk_parameters(signal, symbol, bar, account)
        try:
            decision = self.risk_engine.evaluate_signal(
                params, account, news_context=news_ctx, now=ts
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Risk evaluation error for %s: %s", symbol, exc)
            return

        result.events.append(BacktestEvent(
            EventType.RISK_DECISION, ts, symbol,
            {"signal_id": signal.signal_id, "status": decision.status.value,
             "volume": str(decision.volume) if decision.volume is not None else None},
        ))

        if decision.status.value == "RISK_LOCKED":
            result.risk_lockouts.append({"symbol": symbol, "timestamp": ts.isoformat()})
            return
        if not decision.is_approved:
            result.rejected_signals.append({
                "symbol": symbol,
                "strategy": signal.strategy_name,
                "category": "risk_rejected",
                "reason": "; ".join(decision.rejection_reasons) or decision.status.value,
                "timestamp": ts.isoformat(),
            })
            return
        if decision.volume is None or decision.volume <= 0:
            return

        side = OrderSide.LONG if signal.direction == SignalDirection.LONG else OrderSide.SHORT

        if self.config.execution.fill_on_next_bar:
            order = self.portfolio.order_sim.submit(
                symbol=symbol,
                side=side,
                volume=decision.volume,
                order_type=OrderType.MARKET,
                stop_loss_price=decision.stop_loss_price,
                take_profit_price=decision.take_profit_price,
                strategy_name=signal.strategy_name,
                signal_id=signal.signal_id,
                created_at=ts,
            )
            self._order_risk[order.order_id] = decision.monetary_risk or Decimal("0")
            self._order_bar_index[order.order_id] = self._bar_index
        else:
            fill = self.execution.entry_fill(symbol, side, bar, ref_price=bar.close)
            self.portfolio.open_position(
                symbol=symbol,
                side=side,
                volume=decision.volume,
                fill_price=fill.price,
                fill_time=ts,
                stop_loss_price=decision.stop_loss_price,
                take_profit_price=decision.take_profit_price,
                strategy_name=signal.strategy_name,
                signal_id=signal.signal_id,
                risk_amount=decision.monetary_risk,
                entry_slippage_price=fill.slippage,
            )
            result.events.append(BacktestEvent(
                EventType.FILL, ts, symbol,
                {"price": str(fill.price), "slippage": str(fill.slippage), "immediate": True},
            ))

    # ------------------------------------------------------------------
    # Risk state carry-forward
    # ------------------------------------------------------------------

    def _update_risk_state(self, ts: datetime) -> None:
        equity = self.portfolio.equity(dict(self._last_prices))
        balance = self.portfolio.balance
        day = ts.date()
        if self._current_day is None or day != self._current_day:
            # New simulated day: re-anchor the daily PnL reference to the
            # equity at day start so realized/unrealized PnL accumulates
            # correctly across the day (and is not confused by carry-over
            # open positions from the prior day).
            self._current_day = day
            self._day_start_balance = balance
            self._day_start_equity = equity
            self._day_start_unrealized = equity - balance
        # Keep drawdown high-watermarks current so limits persist across the run.
        try:
            self.risk_engine.drawdown_tracker.update(equity, balance, now=ts)
        except Exception:  # noqa: BLE001
            pass
        # Maintain daily PnL state. DailyPnLState is frozen, so rebuild it
        # each bar from the portfolio's realized + change-in-unrealized PnL.
        realized = balance - self._day_start_balance
        unrealized = (equity - balance) - self._day_start_unrealized
        try:
            self.risk_engine.daily_pnl_state = DailyPnLState(
                starting_balance=self._day_start_balance,
                starting_equity=self._day_start_equity,
                realized_pnl=realized,
                unrealized_pnl=unrealized,
                date=day.isoformat(),
            )
        except Exception:  # noqa: BLE001
            pass

    def _collect_rejections(self) -> List[Dict[str, Any]]:
        return list(self.portfolio.rejected)