"""Event categorization registry.

Configurable keyword→category rules for classifying economic events. An event
is NOT classified HIGH impact merely because its name matches a keyword —
importance comes from provider data plus configurable rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.news.base import EventCategory


@dataclass(frozen=True)
class CategoryRule:
    """Keyword-based category rule."""

    category: EventCategory
    keywords: List[str]
    """Case-insensitive substrings matched against the event name."""


def default_category_rules() -> List[CategoryRule]:
    """Default category keyword rules (extensible)."""
    return [
        CategoryRule(
            EventCategory.INFLATION,
            [
                "cpi", "core cpi", "ppi", "core ppi", "pce", "core pce",
                "inflation", "consumer price", "producer price",
            ],
        ),
        CategoryRule(
            EventCategory.EMPLOYMENT,
            [
                "nonfarm", "nfp", "payroll", "unemployment", "jobless claims",
                "employment change", "wage growth", "average hourly",
                "jobs report", "adp",
            ],
        ),
        CategoryRule(
            EventCategory.CENTRAL_BANK,
            [
                "interest rate", "fomc", "federal reserve", "fed ",
                "ecb", "bank of england", "boe", "bank of japan", "boj",
                "central bank", "rate decision", "policy rate", "speech",
                "powell", "lagarde",
            ],
        ),
        CategoryRule(
            EventCategory.GROWTH,
            [
                "gdp", "pmi", "manufacturing pmi", "services pmi",
                "industrial production", "retail sales",
                "consumer confidence", "ism",
            ],
        ),
        CategoryRule(
            EventCategory.COMMODITIES,
            [
                "eia", "crude oil inventories", "natural gas storage",
                "oil inventory", "petroleum", "energy report",
            ],
        ),
    ]


class CategoryRegistry:
    """Maps event names to categories using configurable keyword rules."""

    def __init__(self, rules: Optional[List[CategoryRule]] = None) -> None:
        self._rules = rules if rules is not None else default_category_rules()

    def classify(self, event_name: str) -> EventCategory:
        """Return the category for an event name (OTHER if no match)."""
        name = event_name.lower()
        for rule in self._rules:
            for kw in rule.keywords:
                if kw in name:
                    return rule.category
        return EventCategory.OTHER

    def register(self, rule: CategoryRule) -> None:
        self._rules = [*self._rules, rule]