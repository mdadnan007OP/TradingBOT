"""News & economic calendar configuration.

Centralized, configurable news policies. Default windows are illustrative only.
Missing/invalid configuration degrades conservatively (block new entries).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from src.news.base import EventCategory, Importance, UnavailablePolicy


@dataclass(frozen=True)
class ImpactWindow:
    """Pre/post-event restriction window for an importance level."""

    pre_minutes: int = 30
    post_minutes: int = 20
    """Illustrative defaults only — tune per strategy/instrument."""


@dataclass(frozen=True)
class CategoryWindows:
    """Optional per-category window overrides."""

    importance_windows: Dict[Importance, ImpactWindow] = field(default_factory=dict)


@dataclass(frozen=True)
class CurrencyRelevanceRule:
    """Relevance rule for an instrument → currencies/events."""

    instrument: str
    currencies: List[str]
    categories: Optional[List[EventCategory]] = None
    """Restrict to these categories (None = all)."""
    include_energy_inventories: bool = False
    """For energy instruments, include commodity-inventory events."""


@dataclass(frozen=True)
class NewsConfig:
    """Complete news engine configuration."""

    version: str = "1.0.0"
    enabled: bool = True

    # Provider selection
    provider_ids: List[str] = field(default_factory=lambda: ["mock"])
    simulated_providers_allowed: bool = True

    # Window defaults per importance
    default_windows: Dict[Importance, ImpactWindow] = field(
        default_factory=lambda: {
            Importance.HIGH: ImpactWindow(pre_minutes=30, post_minutes=20),
            Importance.MEDIUM: ImpactWindow(pre_minutes=15, post_minutes=10),
            Importance.LOW: ImpactWindow(pre_minutes=0, post_minutes=0),
            Importance.UNKNOWN: ImpactWindow(pre_minutes=0, post_minutes=0),
        }
    )
    """Illustrative defaults only; configurable per strategy/instrument."""

    category_window_overrides: Dict[EventCategory, ImpactWindow] = field(
        default_factory=dict
    )
    """Optional per-category overrides (highest priority)."""

    # Caution threshold: events at or above this importance raise NEWS_CAUTION
    caution_importance: Importance = Importance.MEDIUM

    # Unavailable / stale handling
    unavailable_policy: UnavailablePolicy = UnavailablePolicy.BLOCK_NEW_ENTRIES
    stale_after_minutes: int = 240
    """Calendar considered stale if last successful update older than this."""

    # Historical leakage prevention
    prevent_future_leakage: bool = True

    # Currency / instrument relevance mappings (configurable, extensible)
    relevance_rules: List[CurrencyRelevanceRule] = field(
        default_factory=lambda: _default_relevance_rules()
    )

    # Dedup / revision
    dedup_enabled: bool = True

    def get_window(
        self,
        importance: Importance,
        category: Optional[EventCategory] = None,
    ) -> ImpactWindow:
        """Resolve the effective window for an importance + category."""
        if category is not None and category in self.category_window_overrides:
            return self.category_window_overrides[category]
        return self.default_windows.get(
            importance, ImpactWindow(pre_minutes=0, post_minutes=0)
        )

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not self.enabled:
            return ["News engine disabled"]
        for imp, win in self.default_windows.items():
            if win.pre_minutes < 0 or win.post_minutes < 0:
                errors.append(f"Negative window for {imp.value}")
        if self.stale_after_minutes < 0:
            errors.append("stale_after_minutes must be >= 0")
        for rule in self.relevance_rules:
            if not rule.instrument:
                errors.append("Relevance rule missing instrument")
            if not rule.currencies:
                errors.append(f"Relevance rule for {rule.instrument} has no currencies")
        return errors


def _default_relevance_rules() -> List[CurrencyRelevanceRule]:
    """Default instrument → currency/category relevance mappings.

    These are configurable relevance mappings, NOT predictions of market direction.
    """
    return [
        # Forex
        CurrencyRelevanceRule("EURUSD", ["EUR", "USD"]),
        CurrencyRelevanceRule("GBPUSD", ["GBP", "USD"]),
        CurrencyRelevanceRule("USDJPY", ["USD", "JPY"]),
        CurrencyRelevanceRule("AUDUSD", ["AUD", "USD"]),
        CurrencyRelevanceRule("USDCAD", ["USD", "CAD"]),
        # Metals — USD macro + configurable gold/metals events
        CurrencyRelevanceRule("XAUUSD", ["USD"], include_energy_inventories=False),
        CurrencyRelevanceRule("XAGUSD", ["USD"]),
        CurrencyRelevanceRule("XPTUSD", ["USD"]),
        CurrencyRelevanceRule("XPDUSD", ["USD"]),
        # Energy — USD macro + energy inventories
        CurrencyRelevanceRule(
            "WTIUSD", ["USD"], include_energy_inventories=True
        ),
        CurrencyRelevanceRule(
            "BRENTUSD", ["USD"], include_energy_inventories=True
        ),
        CurrencyRelevanceRule(
            "NATGASUSD", ["USD"], include_energy_inventories=True
        ),
        # Indices — relevant national events
        CurrencyRelevanceRule("NAS100", ["USD"]),
        CurrencyRelevanceRule("US500", ["USD"]),
        CurrencyRelevanceRule("US30", ["USD"]),
        CurrencyRelevanceRule("GER40", ["EUR"]),
        CurrencyRelevanceRule("UK100", ["GBP"]),
        # Crypto — USD macro (no central bank currency)
        CurrencyRelevanceRule("BTCUSD", ["USD"]),
        CurrencyRelevanceRule("ETHUSD", ["USD"]),
    ]


def test_news_config(overrides: Optional[Dict[str, object]] = None) -> NewsConfig:
    """Deterministic configuration for automated tests."""
    base = NewsConfig(
        version="test-1.0.0",
        enabled=True,
        provider_ids=["mock"],
        simulated_providers_allowed=True,
        stale_after_minutes=240,
        unavailable_policy=UnavailablePolicy.BLOCK_NEW_ENTRIES,
    )
    if not overrides:
        return base
    from dataclasses import fields as _fields

    allowed = {f.name for f in _fields(NewsConfig)}
    applied: Dict[str, object] = {
        f.name: getattr(base, f.name) for f in _fields(NewsConfig)
    }
    for k, v in overrides.items():
        if k not in allowed:
            raise ValueError(f"Unknown config field: {k}")
        applied[k] = v
    return NewsConfig(**applied)