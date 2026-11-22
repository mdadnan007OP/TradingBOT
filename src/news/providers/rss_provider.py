"""Optional RSS news provider interface for permitted official sources.

Consumes only feeds whose usage is permitted. It never scrapes websites,
bypasses access restrictions, or reuses protected content without permission.
Normal project tests do not require network access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.news.base import NewsProvider
from src.news.models import NewsArticle


@dataclass
class RssNewsProvider(NewsProvider):
    """RSS news provider (interface stub for permitted official feeds)."""

    provider_id: str = "rss"
    feed_urls: List[str] = field(default_factory=list)
    is_simulated: bool = False

    def _fetch_entries(self, start: datetime, end: datetime) -> List[Dict]:
        """Fetch raw feed entries. Override with a permitted feed client.

        Returns empty by default (no live integration / no network in tests).
        """
        return []

    def get_articles(
        self,
        start: datetime,
        end: datetime,
    ) -> List[NewsArticle]:
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        articles: List[NewsArticle] = []
        for entry in self._fetch_entries(start, end):
            published = entry.get("published_time")
            if isinstance(published, str):
                try:
                    published = datetime.fromisoformat(published)
                except ValueError:
                    published = None
            articles.append(
                NewsArticle(
                    article_id=str(entry.get("id", entry.get("url", ""))),
                    source_name=str(entry.get("source", self.provider_id)),
                    headline=str(entry.get("title", "")),
                    url=str(entry.get("url", "")),
                    published_time=published,
                    retrieval_time=datetime.now(timezone.utc),
                    related_currencies=list(entry.get("currencies", [])),
                    duplicate_key=str(entry.get("id", entry.get("url", ""))),
                )
            )
        return articles