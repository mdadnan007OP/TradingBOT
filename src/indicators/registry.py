"""Centralized indicator registry.

Future developers can register new indicators here without modifying the
indicator service itself. The registry keeps indicator formulas separate
from orchestration logic.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.indicators.base import Indicator, IndicatorParameters


class IndicatorRegistry:
    """Centralized registry for indicator implementations.

    Responsibilities:
        * Register an indicator implementation.
        * Retrieve a registered indicator by name.
        * Check whether an indicator name exists.
        * Report all supported indicator names.
        * Expose an indicator's parameter schema.
        * Validate parameters against an indicator's schema.
        * Reject invalid configurations with a clear error.
    """

    def __init__(self) -> None:
        self._indicators: Dict[str, Indicator] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, indicator: Indicator) -> None:
        """Register an indicator implementation.

        Args:
            indicator: An instance of a class implementing :class:`Indicator`.

        Raises:
            TypeError: If ``indicator`` is not an :class:`Indicator`.
            ValueError: If an indicator with the same name is already registered.
        """
        if not isinstance(indicator, Indicator):
            raise TypeError(
                f"Registered object must implement Indicator, got {type(indicator)!r}"
            )
        name = indicator.name
        if name in self._indicators:
            raise ValueError(
                f"Indicator '{name}' is already registered. "
                f"Use a unique name or unregister the existing one first."
            )
        self._indicators[name] = indicator

    def unregister(self, name: str) -> bool:
        """Remove an indicator from the registry.

        Returns True if the indicator was present and removed.
        """
        if name in self._indicators:
            del self._indicators[name]
            return True
        return False

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[Indicator]:
        """Return the registered indicator for ``name``, or None."""
        return self._indicators.get(name)

    def exists(self, name: str) -> bool:
        """Return True if ``name`` is registered."""
        return name in self._indicators

    def supported_indicators(self) -> List[str]:
        """Return a sorted list of all registered indicator names."""
        return sorted(self._indicators.keys())

    def indicator_count(self) -> int:
        """Return the number of registered indicators."""
        return len(self._indicators)

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------

    def parameter_schema(self, name: str) -> Optional[Dict[str, Dict[str, Any]]]:
        """Return the parameter schema for ``name``, or None if unknown."""
        indicator = self.get(name)
        if indicator is None:
            return None
        return indicator.parameter_schema

    def validate_parameters(
        self, name: str, parameters: IndicatorParameters
    ) -> IndicatorParameters:
        """Validate ``parameters`` against ``name``'s schema.

        Returns normalized parameters. Raises ValueError if the indicator is
        unknown or the parameters are invalid.
        """
        indicator = self.get(name)
        if indicator is None:
            raise ValueError(f"Unknown indicator: {name!r}")
        return indicator.validate_parameters(parameters)
