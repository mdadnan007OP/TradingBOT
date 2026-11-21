"""Phase 5 Strategy Engine demonstration script.

Demonstrates the multi-strategy engine generating standardized trading signals
for EURUSD and XAUUSD across multiple timeframes and strategy types.

No orders are placed — this is signal generation only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.indicators import create_engine
from src.market_data.models import DataSource, MarketTimeframe, OHLCBar
from src.strategies import create_strategy_manager


def make_demo_candles(
    n: int = 100,
    start_price: Decimal = Decimal("100"),
    trend: str = "up",
    symbol: str = "EURUSD",
    timeframe: MarketTimeframe = MarketTimeframe.H1,
) -> list:
    """Generate deterministic demo candles."""
    import math

    candles = []
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        if trend == "up":
            close = Decimal(str(start_price + i * Decimal("0.5")))
        elif trend == "down":
            close = Decimal(str(start_price - i * Decimal("0.5")))
        else:
            # Ranging
            offset = Decimal(str(5 * math.sin(i * 0.2)))
            close = Decimal(str(start_price)) + offset

        rng = close * Decimal("0.001")
        open_p = close - rng * Decimal("0.3")
        high_p = close + rng
        low_p = close - rng
        if high_p < max(open_p, close):
            high_p = max(open_p, close) + Decimal("0.0001")
        if low_p > min(open_p, close):
            low_p = min(open_p, close) - Decimal("0.0001")

        candles.append(
            OHLCBar(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=start + timedelta(hours=i),
                open=open_p,
                high=high_p,
                low=low_p,
                close=close,
                tick_volume=100,
                data_source=DataSource.SIMULATED,
            )
        )
    return candles


def demo_signal_generation():
    """Run strategy demonstrations for EURUSD and XAUUSD."""
    print("=" * 70)
    print("PHASE 5 — STRATEGY ENGINE DEMONSTRATION")
    print("=" * 70)
    print()
    print("Mode: Signal generation only (no order execution)")
    print("Data source: Simulated")
    print()

    engine = create_engine()
    manager = create_strategy_manager(engine)

    print("Registered strategies:")
    for info in manager.list_strategies():
        print(f"  - {info['name']} v{info['version']} "
              f"(enabled={info['enabled']})")
    print()

    # Demo scenarios
    scenarios = [
        ("EURUSD", "uptrend", Decimal("108"), MarketTimeframe.H1),
        ("XAUUSD", "downtrend", Decimal("2000"), MarketTimeframe.H4),
        ("EURUSD", "ranging", Decimal("108"), MarketTimeframe.M15),
    ]

    for symbol, trend, start_price, tf in scenarios:
        print(f"{'-' * 70}")
        print(f"Scenario: {symbol} | {trend} | {tf.value}")
        print(f"{'-' * 70}")

        candles = make_demo_candles(
            n=100, start_price=start_price, trend=trend,
            symbol=symbol, timeframe=tf,
        )

        candles_by_tf = {tf: candles}

        # Run all enabled strategies
        results = manager.run_all_enabled(
            symbol=symbol,
            candles_by_timeframe=candles_by_tf,
            data_source=DataSource.SIMULATED,
        )

        for result in results:
            if result.error:
                print(f"  [{result.strategy_name}] ERROR: {result.error}")
                continue

            regime = result.market_regime.value
            print(f"  [{result.strategy_name}] Regime: {regime}")

            if result.signals:
                for sig in result.signals:
                    print(f"    SIGNAL: {sig.direction} | "
                          f"TF: {sig.entry_timeframe.value} | "
                          f"Price: {sig.reference_price} | "
                          f"Invalidation: {sig.technical_invalidation}")
                    print(f"      Explanation: {sig.explanation}")
                    print(f"      Conditions: {', '.join(sig.confirmation_conditions[:3])}")
            else:
                print(f"    No signals generated.")
                if result.rejections:
                    for rej in result.rejections[:2]:
                        print(f"      Rejection: {rej.reason}")

        # Detect conflicts
        conflict_info = manager.detect_conflicts(results)
        if conflict_info["has_conflicts"]:
            print(f"  CONFLICTS DETECTED:")
            for c in conflict_info["conflicts"]:
                print(f"    {c['explanation']}")
        else:
            print(f"  No conflicts — strategies agree or no signals.")

        print()


def demo_conflict_detection():
    """Demonstrate signal conflict detection with opposing strategies."""
    print("=" * 70)
    print("SIGNAL CONFLICT DETECTION DEMO")
    print("=" * 70)
    print()

    engine = create_engine()
    manager = create_strategy_manager(engine)

    # Create mixed market data that could trigger opposing signals
    candles = make_demo_candles(
        n=100, start_price=Decimal("108"), trend="ranging",
        symbol="EURUSD", timeframe=MarketTimeframe.H1,
    )

    results = manager.run_all_enabled(
        symbol="EURUSD",
        candles_by_timeframe={MarketTimeframe.H1: candles},
        data_source=DataSource.SIMULATED,
    )

    agg = manager.aggregate_signals(results, policy="report_conflicts")
    print(f"Aggregation policy: {agg['policy']}")
    print(f"Has conflicts: {agg['has_conflicts']}")
    print(f"Aggregated direction: {agg['aggregated_direction'] or 'None (unresolved)'}")
    print(f"Confidence: {agg['confidence']:.1f}%")
    print(f"Explanation: {agg['explanation']}")
    print()

    if agg["conflicts"]:
        print("Conflicts:")
        for c in agg["conflicts"]:
            print(f"  - {c['explanation']}")

    print()
    print("Agreement groups:")
    for group in agg["agreement_groups"]:
        print(f"  - {', '.join(group)}")

    print()
    print("Signal details:")
    for detail in agg["signal_details"]:
        print(f"  - {detail['strategy']}: {detail['direction']} "
              f"({detail['timeframe']})")


def main():
    demo_signal_generation()
    print()
    demo_conflict_detection()
    print()
    print("=" * 70)
    print("DEMONSTRATION COMPLETE — No orders were placed.")
    print("=" * 70)


if __name__ == "__main__":
    main()
