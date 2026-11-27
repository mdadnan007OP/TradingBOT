"""Phase 10 — Notification and alert system.

Supports optional providers: Email (SMTP), Telegram Bot API, configurable webhook,
and local log output. All credentials are read from environment variables — never
stored in source code. All external integrations are optional.

Alert categories: Critical, High, Medium, Informational.
Implements alert deduplication, rate limiting, notification failure handling,
alert history, and delivery status.
Never reports an alert as delivered without a confirmed delivery response.
Never sends secrets in notification messages.
"""

from __future__ import annotations

import json
import logging
import re
import smtplib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    INFO = "info"


@dataclass
class Alert:
    """An alert record."""

    id: str
    severity: AlertSeverity
    title: str
    message: str
    component: str
    timestamp: datetime
    delivered: bool = False
    delivery_error: Optional[str] = None
    dedup_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "component": self.component,
            "timestamp": self.timestamp.isoformat(),
            "delivered": self.delivered,
            "delivery_error": self.delivery_error,
            "dedup_key": self.dedup_key,
        }


class NotificationProvider:
    """Abstract notification provider."""

    name: str = "base"

    def send(self, alert: Alert) -> bool:
        """Send a notification. Returns True if delivery was confirmed."""
        raise NotImplementedError

    def redact_secrets(self, text: str) -> str:
        """Redact potential secrets from text before sending."""
        import re

        # Redact common secret patterns.
        patterns = [
            (r"[A-Za-z0-9+/=]{40,}", "[REDACTED_TOKEN]"),  # Long tokens
            (r"sk-[A-Za-z0-9]{20,}", "[REDACTED_API_KEY]"),  # API key pattern
            (r"bot\d+:[A-Za-z0-9_-]{30,}", "[REDACTED_BOT_TOKEN]"),  # Telegram bot token
        ]
        result = text
        for pattern, replacement in patterns:
            result = re.sub(pattern, replacement, result)
        return result


class LogProvider(NotificationProvider):
    """Local log output provider (always available, optional)."""

    name = "log"

    def send(self, alert: Alert) -> bool:
        redacted_message = self.redact_secrets(alert.message)
        redacted_title = self.redact_secrets(alert.title)
        log_msg = f"ALERT [{alert.severity.value.upper()}] {alert.component}: {redacted_title} - {redacted_message}"
        if alert.severity == AlertSeverity.CRITICAL:
            logger.critical(log_msg)
        elif alert.severity == AlertSeverity.HIGH:
            logger.error(log_msg)
        elif alert.severity == AlertSeverity.MEDIUM:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)
        alert.delivered = True
        return True


class EmailProvider(NotificationProvider):
    """SMTP email notification provider (optional)."""

    name = "email"

    def __init__(self, config: Any) -> None:
        self._config = config

    def send(self, alert: Alert) -> bool:
        if not self._config.email_smtp_host or not self._config.email_to:
            logger.warning("Email provider not fully configured; skipping delivery")
            return False
        try:
            msg = EmailMessage()
            msg["Subject"] = f"[Trading Bot {alert.severity.value.upper()}] {self.redact_secrets(alert.title)}"
            msg["From"] = self._config.email_from or "trading-bot@localhost"
            msg["To"] = ", ".join(self._config.email_to)
            body = (
                f"Component: {alert.component}\n"
                f"Severity: {alert.severity.value}\n"
                f"Time: {alert.timestamp.isoformat()}\n"
                f"Message: {self.redact_secrets(alert.message)}\n"
            )
            msg.set_content(body)

            with smtplib.SMTP(self._config.email_smtp_host, self._config.email_smtp_port, timeout=10) as smtp:
                if self._config.email_use_tls:
                    smtp.starttls()
                if self._config.email_smtp_user and self._config.email_smtp_password:
                    smtp.login(self._config.email_smtp_user, self._config.email_smtp_password)
                smtp.send_message(msg)

            alert.delivered = True
            return True
        except Exception as exc:  # noqa: BLE001
            logger.exception("Email delivery failed: %s", exc)
            alert.delivered = False
            alert.delivery_error = str(exc)
            return False


class TelegramProvider(NotificationProvider):
    """Telegram Bot API notification provider (optional)."""

    name = "telegram"

    def __init__(self, config: Any) -> None:
        self._config = config

    def send(self, alert: Alert) -> bool:
        if not self._config.telegram_bot_token or not self._config.telegram_chat_id:
            logger.warning("Telegram provider not fully configured; skipping delivery")
            return False
        try:
            text = (
                f"*[{alert.severity.value.upper()}] {self.redact_secrets(alert.title)}*\n"
                f"Component: {alert.component}\n"
                f"Time: {alert.timestamp.isoformat()}\n"
                f"{self.redact_secrets(alert.message)}"
            )
            url = (
                f"https://api.telegram.org/bot{self._config.telegram_bot_token}"
                f"/sendMessage"
            )
            payload = json.dumps(
                {"chat_id": self._config.telegram_chat_id, "text": text, "parse_mode": "Markdown"}
            ).encode("utf-8")
            req = Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    alert.delivered = True
                    return True
                alert.delivered = False
                alert.delivery_error = f"HTTP {resp.status}"
                return False
        except (URLError, HTTPError) as exc:
            logger.exception("Telegram delivery failed: %s", exc)
            alert.delivered = False
            alert.delivery_error = str(exc)
            return False


class WebhookProvider(NotificationProvider):
    """Configurable webhook notification provider (optional)."""

    name = "webhook"

    def __init__(self, config: Any) -> None:
        self._config = config

    def send(self, alert: Alert) -> bool:
        if not self._config.webhook_url:
            logger.warning("Webhook provider not configured; skipping delivery")
            return False
        try:
            payload = json.dumps(alert.to_dict()).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            if self._config.webhook_secret:
                headers["X-Webhook-Secret"] = self.redact_secrets(self._config.webhook_secret)
            req = Request(self._config.webhook_url, data=payload, headers=headers)
            with urlopen(req, timeout=10) as resp:
                if 200 <= resp.status < 300:
                    alert.delivered = True
                    return True
                alert.delivered = False
                alert.delivery_error = f"HTTP {resp.status}"
                return False
        except (URLError, HTTPError) as exc:
            logger.exception("Webhook delivery failed: %s", exc)
            alert.delivered = False
            alert.delivery_error = str(exc)
            return False


@dataclass
class AlertConfigSnapshot:
    """Snapshot of alert configuration for the AlertManager."""

    enabled: bool = False
    providers: List[str] = field(default_factory=list)
    rate_limit_seconds: int = 60
    dedup_window_seconds: int = 300
    max_history_items: int = 1000
    email_smtp_host: str = ""
    email_smtp_port: int = 587
    email_smtp_user: str = ""
    email_smtp_password: str = ""
    email_from: str = ""
    email_to: List[str] = field(default_factory=list)
    email_use_tls: bool = True
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    webhook_url: str = ""
    webhook_secret: str = ""


class AlertManager:
    """Manages alerts: creation, deduplication, rate limiting, delivery, history."""

    def __init__(self, config: AlertConfigSnapshot) -> None:
        self._config = config
        self._alerts: List[Alert] = []
        self._providers: Dict[str, NotificationProvider] = {}
        self._last_alert_time: Dict[str, float] = {}  # dedup_key -> last send time
        self._last_delivery_time: float = 0.0  # global rate limit

        self._init_providers()

    def _init_providers(self) -> None:
        if not self._config.enabled:
            logger.info("Alert notifications are disabled")
            return

        # Log provider is always available if alerts enabled.
        self._providers["log"] = LogProvider()

        if "email" in self._config.providers:
            self._providers["email"] = EmailProvider(self._config)
        if "telegram" in self._config.providers:
            self._providers["telegram"] = TelegramProvider(self._config)
        if "webhook" in self._config.providers:
            self._providers["webhook"] = WebhookProvider(self._config)

        logger.info(
            "Alert providers initialized: %s", ", ".join(self._providers.keys())
        )

    def _dedup_key(
        self, severity: AlertSeverity, title: str, component: str
    ) -> str:
        import hashlib

        material = f"{severity.value}|{title}|{component}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]

    def _is_rate_limited(self) -> bool:
        now = time.time()
        if now - self._last_delivery_time < self._config.rate_limit_seconds:
            return True
        return False

    def _is_dup(self, dedup_key: str) -> bool:
        now = time.time()
        last = self._last_alert_time.get(dedup_key, 0)
        if now - last < self._config.dedup_window_seconds:
            return True
        return False

    def _record_delivery(self, dedup_key: str) -> None:
        now = time.time()
        self._last_alert_time[dedup_key] = now
        self._last_delivery_time = now

    def _prune_history(self) -> None:
        max_items = self._config.max_history_items
        if len(self._alerts) > max_items:
            self._alerts = self._alerts[-max_items:]

    def send_alert(
        self,
        *,
        severity: AlertSeverity,
        title: str,
        message: str,
        component: str = "system",
        dedup_key: Optional[str] = None,
    ) -> Alert:
        """Create and attempt to deliver an alert.

        Never reports an alert as delivered without a confirmed delivery response.
        Never sends secrets in notification messages.
        """
        if not self._config.enabled:
            return Alert(
                id="",
                severity=severity,
                title=title,
                message=message,
                component=component,
                timestamp=datetime.now(timezone.utc),
                delivered=False,
                delivery_error="notifications disabled",
            )

        if dedup_key is None:
            dedup_key = self._dedup_key(severity, title, component)

        # Deduplication (checked first - more specific than rate limit).
        if self._is_dup(dedup_key):
            logger.debug("Alert duplicate suppressed: %s", title)
            return Alert(
                id="",
                severity=severity,
                title=title,
                message=message,
                component=component,
                timestamp=datetime.now(timezone.utc),
                delivered=False,
                delivery_error="duplicate suppressed",
                dedup_key=dedup_key,
            )

        # Rate limiting.
        if self._is_rate_limited():
            logger.debug("Alert rate-limited: %s", title)
            return Alert(
                id="",
                severity=severity,
                title=title,
                message=message,
                component=component,
                timestamp=datetime.now(timezone.utc),
                delivered=False,
                delivery_error="rate limited",
                dedup_key=dedup_key,
            )

        alert = Alert(
            id=dedup_key,
            severity=severity,
            title=title,
            message=message,
            component=component,
            timestamp=datetime.now(timezone.utc),
            dedup_key=dedup_key,
        )

        # Deliver via all configured providers.
        delivered_any = False
        for name, provider in self._providers.items():
            try:
                if provider.send(alert):
                    delivered_any = True
            except Exception as exc:  # noqa: BLE001
                logger.exception("Provider %s failed: %s", name, exc)

        if delivered_any:
            alert.delivered = True
            self._record_delivery(dedup_key)
        else:
            alert.delivered = False
            alert.delivery_error = "all providers failed"

        self._alerts.append(alert)
        self._prune_history()
        return alert

    def get_alerts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recent alerts as dictionaries."""
        return [a.to_dict() for a in self._alerts[-limit:]]

    def get_undelivered(self) -> List[Dict[str, Any]]:
        """Return alerts that were not delivered."""
        return [a.to_dict() for a in self._alerts if not a.delivered]

    @property
    def provider_names(self) -> List[str]:
        return list(self._providers.keys())
