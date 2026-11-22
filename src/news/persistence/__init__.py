"""Persistence: event repository and revision history."""

from __future__ import annotations

from src.news.persistence.repository import EventRepository
from src.news.persistence.event_history import EventHistory

__all__ = ["EventRepository", "EventHistory"]