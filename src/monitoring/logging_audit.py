"""Phase 10 — Structured logging and audit trails.

Supports structured JSON logging with correlation IDs, event IDs, and sensitive
data redaction. Log rotation, retention policies, and separate error logs are
configured via the monitoring configuration.

Never logs: broker passwords, API keys, authentication tokens, or unnecessary
account identifiers.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# Patterns for sensitive data redaction.
_SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"bot\d+:[A-Za-z0-9_-]{30,}"), "[REDACTED_BOT_TOKEN]"),
    (re.compile(r"password[=:]\s*\S+", re.IGNORECASE), "password=[REDACTED]"),
    (re.compile(r"api[_-]?key[=:]\s*\S+", re.IGNORECASE), "api_key=[REDACTED]"),
    (re.compile(r"secret[=:]\s*\S+", re.IGNORECASE), "secret=[REDACTED]"),
    (re.compile(r"token[=:]\s*\S+", re.IGNORECASE), "token=[REDACTED]"),
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "[REDACTED_CARD]"),
]


def redact_secrets(text: str) -> str:
    """Redact potential secrets from a string."""
    if not text:
        return text
    result = text
    for pattern, replacement in _SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


@dataclass
class AuditEvent:
    """A structured audit event."""

    event_id: str
    timestamp: str
    component: str
    severity: str
    execution_id: Optional[str] = None
    signal_id: Optional[str] = None
    correlation_id: Optional[str] = None
    result: Optional[str] = None
    error_classification: Optional[str] = None
    message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Redact secrets in message and metadata.
        if d.get("message"):
            d["message"] = redact_secrets(d["message"])
        if d.get("metadata"):
            d["metadata"] = {
                k: redact_secrets(str(v)) for k, v in d["metadata"].items()
            }
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


class StructuredLogger:
    """Structured logger that emits JSON audit events."""

    def __init__(
        self,
        name: str = "trading_bot.audit",
        log_dir: Optional[str] = None,
        max_file_mb: int = 5,
        retention_days: int = 30,
        redact_secrets: bool = True,
    ) -> None:
        self.name = name
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.DEBUG)
        self._redact_secrets = redact_secrets

        # Prevent duplicate handlers.
        if self._logger.handlers:
            return

        formatter = logging.Formatter("%(message)s")

        # Console handler.
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        self._logger.addHandler(console)

        # Optional rotating file handler.
        target_dir = log_dir
        if target_dir:
            try:
                os.makedirs(target_dir, exist_ok=True)
                log_path = os.path.join(target_dir, "audit.log")
                fh = logging.handlers.RotatingFileHandler(
                    log_path, maxBytes=max_file_mb * 1_000_000, backupCount=3,
                    encoding="utf-8",
                )
                fh.setFormatter(formatter)
                self._logger.addHandler(fh)
            except OSError as exc:
                # Never silently discard - log to console at least.
                logger.warning("Could not initialize audit file logging: %s", exc)

        # Separate error log.
        if target_dir:
            try:
                error_path = os.path.join(target_dir, "audit_errors.log")
                efh = logging.handlers.RotatingFileHandler(
                    error_path, maxBytes=max_file_mb * 1_000_000,
                    backupCount=3, encoding="utf-8",
                )
                efh.setLevel(logging.ERROR)
                efh.setFormatter(formatter)
                self._logger.addHandler(efh)
            except OSError as exc:
                logger.warning("Could not initialize audit error logging: %s", exc)

    def log_event(
        self,
        *,
        component: str,
        severity: str = "info",
        execution_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        result: Optional[str] = None,
        error_classification: Optional[str] = None,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """Log a structured audit event."""
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            component=component,
            severity=severity,
            execution_id=execution_id,
            signal_id=signal_id,
            correlation_id=correlation_id,
            result=result,
            error_classification=error_classification,
            message=redact_secrets(message) if self._redact_secrets else message,
            metadata={
                k: redact_secrets(str(v)) for k, v in (metadata or {}).items()
            } if self._redact_secrets else (metadata or {}),
        )
        self._logger.info(event.to_json())
        return event

    def log_execution_event(
        self,
        *,
        component: str,
        execution_id: str,
        result: str,
        severity: str = "info",
        signal_id: Optional[str] = None,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """Log an execution-related audit event."""
        return self.log_event(
            component=component,
            severity=severity,
            execution_id=execution_id,
            signal_id=signal_id,
            result=result,
            message=message,
            metadata=metadata,
        )

    def log_security_event(
        self,
        *,
        component: str,
        result: str,
        severity: str = "warning",
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """Log a security-related audit event."""
        return self.log_event(
            component=component,
            severity=severity,
            result=result,
            error_classification="security",
            message=message,
            metadata=metadata,
        )


# Global structured logger instance.
structured_logger = StructuredLogger(
    redact_secrets=True,
)


def get_structured_logger() -> StructuredLogger:
    return structured_logger
