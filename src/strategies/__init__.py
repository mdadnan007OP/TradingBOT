"""Strategy Engine package.

Phase 5 — Multi-Strategy Engine for signal generation.

Provides a modular, extensible framework for building and running trading
strategies that produce standardized ``Signal`` objects (LONG / SHORT / NONE).

The engine does not place orders. It is a signal-generation phase only.

Built-in strategies are registered automatically on import. Use
:func:`create_strategy_manager` to obtain a :class:`StrategyManager` with
all built-in strategies registered.
"""

from __future__ import annotations

from typing import Optional

from src.strategies.base import (
    MarketRegime,
    Signal,
    SignalDirection,
    SignalStatus,
    SignalRejection,
    SignalGenerationContext,
    Strategy,
    StrategyResult,
)
from src.strategies.conflict_resolver import (
    SignalConflict,
    SignalConflictResolver,
    ConflictDetectionResult,
)
from src.strategies.market_regime import MarketRegimeDetector, MarketRegimeResult
from src.strategies.models import (
    ConfirmationCondition,
    ConfirmationRule,
    IndicatorSnapshot,
    StrategyParameters,
)
from src.strategies.registry import StrategyRegistry
from src.strategies.service import SignalService
from src.strategies.manager import StrategyManager
from src.strategies.signal_generator import (
    ConfirmationEvaluator,
    SignalGenerator,
)

# --- Built-in strategy modules (imported to trigger registration) ---
from src.strategies.trend_following import (  # noqa: F401
    TrendFollowingStrategy,
)
from src.strategies.price_action import (  # noqa: F401
    PriceActionStrategy,
)
from src.strategies.liquidity import (  # noqa: F401
    LiquidityHuntingStrategy,
)
from src.strategies.trendline import (  # noqa: F401
    TrendlineStrategy,
)
from src.strategies.daily_levels import (  # noqa: F401
    DailyHighLowStrategy,
)
from src.strategies.scalping import (  # noqa: F401
    ScalpingProfile,
)
from src.strategies.intraday import (  # noqa: F401
    IntradayProfile,
)
from src.strategies.swing import (  # noqa: F401
    SwingProfile,
)

__version__ = "0.5.0"

__all__ = [
    # Base
    "Strategy",
    "Signal",
    "SignalDirection",
    "SignalStatus",
    "MarketRegime",
    "SignalRejection",
    "StrategyResult",
    "SignalGenerationContext",
    # Registry
    "StrategyRegistry",
    # Models
    "StrategyParameters",
    "ConfirmationCondition",
    "ConfirmationRule",
    "IndicatorSnapshot",
    # Service
    "SignalService",
    # Manager
    "StrategyManager",
    # Signal generator
    "SignalGenerator",
    "ConfirmationEvaluator",
    # Conflict resolver
    "SignalConflictResolver",
    "SignalConflict",
    "ConflictDetectionResult",
    # Market regime
    "MarketRegimeDetector",
    "MarketRegimeResult",
    # Built-in strategies
    "TrendFollowingStrategy",
    "PriceActionStrategy",
    "LiquidityHuntingStrategy",
    "TrendlineStrategy",
    "DailyHighLowStrategy",
    "ScalpingProfile",
    "IntradayProfile",
    "SwingProfile",
    # Factory
    "create_strategy_manager",
]


# ---------------------------------------------------------------------------
# Auto-registration of built-in strategies
# ---------------------------------------------------------------------------

_DEFAULT_REGISTRY: Optional[StrategyRegistry] = None


def _default_registry() -> StrategyRegistry:
    """Lazily build and populate the default registry with all built-ins."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        registry = StrategyRegistry()
        registry.register(TrendFollowingStrategy())
        registry.register(PriceActionStrategy())
        registry.register(LiquidityHuntingStrategy())
        registry.register(TrendlineStrategy())
        registry.register(DailyHighLowStrategy())
        registry.register(ScalpingProfile())
        registry.register(IntradayProfile())
        registry.register(SwingProfile())
        _DEFAULT_REGISTRY = registry
    return _DEFAULT_REGISTRY


def create_strategy_manager(
    indicator_engine: Any,
) -> StrategyManager:
    """Create a :class:`StrategyManager` with all built-in strategies registered.

    Args:
        indicator_engine: An :class:`IndicatorEngine` instance from Phase 4.

    Returns:
        A configured :class:`StrategyManager` with all built-in strategies
        registered and enabled.
    """
    registry = _default_registry()
    service = SignalService(indicator_engine=indicator_engine)
    manager = StrategyManager(
        indicator_engine=indicator_engine,
        registry=registry,
    )
    return manager
