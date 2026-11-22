"""Risk integration: adapters between the news engine and Phase 6 risk.

The Phase 6 Risk Management Engine remains backward-compatible: news is passed
as an *optional* ``NewsRiskContext``. When ``None``, no news gate applies.
"""

from __future__ import annotations

from src.news.models import NewsRiskContext
from src.news.risk_integration.news_risk_context import (
    summarize_news_context,
)

__all__ = ["NewsRiskContext", "summarize_news_context"]