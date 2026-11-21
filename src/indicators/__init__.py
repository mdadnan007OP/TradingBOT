"""Technical Indicator Engine package.

Provides a modular, extensible engine for calculating technical indicators
from standardized OHLC candles produced by the Phase 2 Market Data Engine.

All indicators are:
- Stateless: ``calculate`` returns a new result without mutating inputs.
- Source-aware: results carry ``data_source`` provenance so simulated values
  are never mistaken for genuine MT5 calculations.
- Look-ahead safe: completed candles are used by default; unfinished candles
  are handled only when explicitly opted into.
- Multi-timeframe: calculations are performed per symbol/timeframe.

The engine does not depend on the MetaTrader5 package and works equally with
simulated, historical CSV, and MT5-originated candles.

Built-in indicators are registered automatically on import. Use
:func:`create_engine` to obtain an :class:`IndicatorEngine` with all built-ins
registered, or construct an :class:`IndicatorEngine` and register indicators
individually.
"""

from __future__ import annotations

from typing import Optional

from src.indicators.base import (
    Indicator,
    IndicatorParameters,
    IndicatorResult,
    ReadinessStatus,
)
from src.indicators.registry import IndicatorRegistry
from src.indicators.service import IndicatorEngine

# --- Built-in indicator modules (imported to trigger side-effect registration) ---
from src.indicators.trend import (  # noqa: F401
    ADXIndicator,
    EMAIndicator,
    IchimokuIndicator,
    SMAIndicator,
)
from src.indicators.momentum import (  # noqa: F401
    CCIIndicator,
    MACDIndicator,
    RSIIndicator,
    StochasticIndicator,
    WilliamsRIndicator,
)
from src.indicators.volatility import (  # noqa: F401
    ATRIndicator,
    BollingerBandsIndicator,
)
from src.indicators.volume import (  # noqa: F401
    VWAPIndicator,
)
from src.indicators.levels import (  # noqa: F401
    ClassicPivotPointsIndicator,
)

__version__ = "0.4.0"

__all__ = [
    "Indicator",
    "IndicatorParameters",
    "IndicatorResult",
    "ReadinessStatus",
    "IndicatorRegistry",
    "IndicatorEngine",
    "create_engine",
    # Built-in indicators
    "SMAIndicator",
    "EMAIndicator",
    "ADXIndicator",
    "IchimokuIndicator",
    "RSIIndicator",
    "MACDIndicator",
    "StochasticIndicator",
    "CCIIndicator",
    "WilliamsRIndicator",
    "ATRIndicator",
    "BollingerBandsIndicator",
    "VWAPIndicator",
    "ClassicPivotPointsIndicator",
]


# ---------------------------------------------------------------------------
# Auto-registration of built-in indicators
# ---------------------------------------------------------------------------

_DEFAULT_REGISTRY: Optional[IndicatorRegistry] = None


def _default_registry() -> IndicatorRegistry:
    """Lazily build and populate the default registry with all built-ins."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        registry = IndicatorRegistry()
        registry.register(SMAIndicator())
        registry.register(EMAIndicator())
        registry.register(ADXIndicator())
        registry.register(IchimokuIndicator())
        registry.register(RSIIndicator())
        registry.register(MACDIndicator())
        registry.register(StochasticIndicator())
        registry.register(CCIIndicator())
        registry.register(WilliamsRIndicator())
        registry.register(ATRIndicator())
        registry.register(BollingerBandsIndicator())
        registry.register(VWAPIndicator())
        registry.register(ClassicPivotPointsIndicator())
        _DEFAULT_REGISTRY = registry
    return _DEFAULT_REGISTRY


def create_engine() -> IndicatorEngine:
    """Create an :class:`IndicatorEngine` with all built-in indicators registered."""
    return IndicatorEngine(registry=_default_registry())
