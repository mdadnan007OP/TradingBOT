"""Phase 7: News & Economic Calendar Engine.

Collects, normalizes and evaluates economic-calendar events and news, then
communicates event-related restrictions to the Phase 6 Risk Management Engine.
This package never places, modifies or closes orders and never executes trades.

Public API:
    Models:    EconomicEvent, NewsArticle, ImpactAssessment, NewsRiskContext
    Enums:     Importance, EventStatus, NewsWindowStatus, EventCategory,
               UnavailablePolicy
    Providers: MockCalendarProvider, MockNewsProvider, CsvCalendarProvider,
               MT5CalendarProvider, ApiCalendarProvider, RssNewsProvider
    Service:   NewsService, NewsConfig, test_news_config
    Filters:   build_news_risk_context, compute_news_window_status
"""

from __future__ import annotations

from src.news.base import (
    CalendarProvider,
    EventCategory,
    EventStatus,
    Importance,
    NewsEngineABC,
    NewsProvider,
    NewsWindowStatus,
    UnavailablePolicy,
)
from src.news.config import (
    CategoryWindows,
    CurrencyRelevanceRule,
    ImpactWindow,
    NewsConfig,
    test_news_config,
)
from src.news.models import (
    EconomicEvent,
    ImpactAssessment,
    NewsArticle,
    NewsRiskContext,
)
from src.news.registry import CategoryRegistry, CategoryRule, default_category_rules
from src.news.service import NewsService
from src.news.filters.restriction import build_news_risk_context
from src.news.filters.news_window import compute_news_window_status
from src.news.providers.mock_provider import MockCalendarProvider, MockNewsProvider
from src.news.providers.csv_provider import CsvCalendarProvider
from src.news.providers.mt5_calendar_provider import MT5CalendarProvider
from src.news.providers.api_provider import ApiCalendarProvider
from src.news.providers.rss_provider import RssNewsProvider

__all__ = [
    # Enums / base
    "Importance",
    "EventStatus",
    "NewsWindowStatus",
    "EventCategory",
    "UnavailablePolicy",
    "CalendarProvider",
    "NewsProvider",
    "NewsEngineABC",
    # Models
    "EconomicEvent",
    "NewsArticle",
    "ImpactAssessment",
    "NewsRiskContext",
    # Config
    "NewsConfig",
    "ImpactWindow",
    "CategoryWindows",
    "CurrencyRelevanceRule",
    "test_news_config",
    # Registry
    "CategoryRegistry",
    "CategoryRule",
    "default_category_rules",
    # Service
    "NewsService",
    # Filters
    "build_news_risk_context",
    "compute_news_window_status",
    # Providers
    "MockCalendarProvider",
    "MockNewsProvider",
    "CsvCalendarProvider",
    "MT5CalendarProvider",
    "ApiCalendarProvider",
    "RssNewsProvider",
]