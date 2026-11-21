"""Strategy registry — centralized registration and lifecycle management.

Strategies register themselves here. The registry supports enable/disable,
parameter storage, and lookup by name. One failed strategy registration does
not affect others.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.strategies.base import (
    MarketRegime,
    SignalDirection,
    SignalStatus,
    Strategy,
)


class StrategyRegistry:
    """Centralized registry for strategy implementations.

    Responsibilities:
        * Register strategy implementations.
        * Retrieve strategies by name.
        * Enable/disable strategies.
        * Store per-strategy parameters.
        * Report available strategies and their capabilities.
    """

    def __init__(self) -> None:
        self._strategies: Dict[str, Strategy] = {}
        self._strategy_parameters: Dict[str, Dict[str, Any]] = {}
        self._enabled: set[str] = set()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, strategy: Strategy) -> bool:
        """Register a strategy implementation.

        Args:
            strategy: A Strategy instance.

        Returns:
            True if registered, False if a strategy with the same name
            already exists.
        """
        name = strategy.name
        if name in self._strategies:
            return False
        self._strategies[name] = strategy
        self._strategy_parameters[name] = dict(strategy.default_parameters.values)
        self._enabled.add(name)
        return True

    def unregister(self, name: str) -> bool:
        """Remove a strategy from the registry.

        Returns True if the strategy was present and removed.
        """
        if name not in self._strategies:
            return False
        del self._strategies[name]
        self._strategy_parameters.pop(name, None)
        self._enabled.discard(name)
        return True

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[Strategy]:
        """Return the strategy for ``name``, or None."""
        return self._strategies.get(name)

    def exists(self, name: str) -> bool:
        """Return True if ``name`` is registered."""
        return name in self._strategies

    def supported_strategies(self) -> List[str]:
        """Return a sorted list of all registered strategy names."""
        return sorted(self._strategies.keys())

    def enabled_strategies(self) -> List[str]:
        """Return a sorted list of enabled strategy names."""
        return sorted(s for s in self._enabled if s in self._strategies)

    def disabled_strategies(self) -> List[str]:
        """Return a sorted list of disabled strategy names."""
        return sorted(s for s in self._strategies if s not in self._enabled)

    def strategy_count(self) -> int:
        """Return the number of registered strategies."""
        return len(self._strategies)

    # ------------------------------------------------------------------
    # Enable / disable
    # ------------------------------------------------------------------

    def enable(self, name: str) -> bool:
        """Enable a registered strategy.

        Returns True if the strategy exists and was enabled.
        """
        if name not in self._strategies:
            return False
        self._enabled.add(name)
        strategy = self._strategies[name]
        strategy.enable()
        return True

    def disable(self, name: str) -> bool:
        """Disable a registered strategy.

        Returns True if the strategy exists and was disabled.
        """
        if name not in self._strategies:
            return False
        self._enabled.discard(name)
        strategy = self._strategies[name]
        strategy.disable()
        return True

    def is_enabled(self, name: str) -> bool:
        """Return True if ``name`` is registered and enabled."""
        return name in self._enabled and name in self._strategies

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------

    def set_parameters(
        self, name: str, parameters: Dict[str, Any]
    ) -> bool:
        """Store custom parameters for a strategy.

        Returns True if the strategy exists.
        """
        if name not in self._strategies:
            return False
        self._strategy_parameters[name] = dict(parameters)
        return True

    def get_parameters(self, name: str) -> Optional[Dict[str, Any]]:
        """Return stored parameters for a strategy, or None."""
        return dict(self._strategy_parameters.get(name, {}))

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------

    def required_timeframes(self, name: str) -> Optional[List[str]]:
        """Return required timeframes for a strategy, or None."""
        strategy = self._strategies.get(name)
        if strategy is None:
            return None
        return [tf.value for tf in strategy.required_timeframes]

    def supported_regimes(self, name: str) -> Optional[List[str]]:
        """Return supported market regimes for a strategy, or None."""
        strategy = self._strategies.get(name)
        if strategy is None:
            return None
        return [r.value for r in strategy.supported_regimes]

    def strategy_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Return a capability summary for a strategy."""
        strategy = self._strategies.get(name)
        if strategy is None:
            return None
        return {
            "name": strategy.name,
            "version": strategy.version,
            "enabled": self.is_enabled(name),
            "required_timeframes": [tf.value for tf in strategy.required_timeframes],
            "supported_instruments": strategy.supported_instruments,
            "supported_regimes": [r.value for r in strategy.supported_regimes],
            "default_parameters": dict(strategy.default_parameters.values),
        }
