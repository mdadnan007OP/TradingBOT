"""Event → currency/instrument mapping.

Determines which currencies (and therefore which instruments) an event is
relevant to, using configurable relevance rules from NewsConfig.
"""

from __future__ import annotations

from typing import List, Optional

from src.news.base import EventCategory
from src.news.config import CurrencyRelevanceRule, NewsConfig
from src.news.models import EconomicEvent


def currencies_for_instrument(
    instrument: str,
    config: NewsConfig,
) -> List[str]:
    """Return the currencies an instrument is sensitive to."""
    for rule in config.relevance_rules:
        if rule.instrument.upper() == instrument.upper():
            return [c.upper() for c in rule.currencies]
    return []


def instrument_is_relevant(
    instrument: str,
    event: EconomicEvent,
    config: NewsConfig,
) -> bool:
    """Return True if the event is relevant to the instrument.

    Relevance = event currency is in the instrument's currency set, optionally
    restricted to configured categories, plus energy-inventory inclusion for
    energy instruments.
    """
    rule = _find_rule(instrument, config)
    if rule is None:
        return False

    if event.currency.upper() not in [c.upper() for c in rule.currencies]:
        # Energy-inventory events (commodities) can be relevant to energy
        # instruments even when currency differs.
        if rule.include_energy_inventories and event.category == EventCategory.COMMODITIES:
            return True
        return False

    if rule.categories is not None:
        return event.category in rule.categories
    return True


def _find_rule(
    instrument: str, config: NewsConfig
) -> Optional[CurrencyRelevanceRule]:
    for rule in config.relevance_rules:
        if rule.instrument.upper() == instrument.upper():
            return rule
    return None