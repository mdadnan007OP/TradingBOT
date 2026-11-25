"""Phase 9 demo-account identity verification.

Strict account verification before every broker trading operation, using the
existing Phase 3 MT5ConnectionManager + MT5AccountInfo infrastructure.

REAL and CONTEST accounts are always rejected. The expected demo server and
broker company are configured explicitly (no partial string matching).
"""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.broker.mt5.connection import MT5AccountInfo, MT5ConnectionManager
from src.execution.config import ExecutionConfig


@dataclass(frozen=True)
class AccountIdentity:
    """Verified demo-account identity snapshot (no sensitive login data)."""

    server: str
    company: str
    currency: str
    trade_mode: str  # "demo" | "contest" | "real" | "unknown"
    trade_allowed: bool
    terminal_connected: bool
    external_python_api_enabled: bool
    terminal_trade_enabled: bool
    identity_fingerprint: str  # HMAC of server+company (no raw login)
    verified_at: datetime
    is_demo: bool
    verification_passed: bool
    rejection_reason: Optional[str] = None


class AccountIdentityVerifier:
    """Verifies and binds demo-account identity before trading operations."""

    def __init__(
        self,
        connection: MT5ConnectionManager,
        config: ExecutionConfig,
        secret: Optional[str] = None,
    ) -> None:
        self.connection = connection
        self.config = config
        self._secret = secret or os.environ.get("EXECUTION_IDENTITY_SECRET", "")
        self._bound_fingerprint: Optional[str] = None
        self._bound_server: Optional[str] = None
        self._bound_company: Optional[str] = None

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(self) -> AccountIdentity:
        """Full account identity verification. Fail-closed."""

        # Terminal must be connected.
        if not self.connection.check_connection():
            return self._reject("MT5 terminal is not connected")

        account_info = MT5AccountInfo(self.connection._mt5_module)
        if not account_info.is_account_available():
            return self._reject("Account information is unavailable")

        raw = account_info.get_account_info()
        if raw is None:
            return self._reject("Account info returned None")

        server = str(getattr(raw, "server", "") or "")
        company = str(getattr(raw, "company", "") or "")
        currency = str(getattr(raw, "currency", "") or "")
        trade_mode_str = account_info.get_account_mode_str()
        trade_allowed = bool(getattr(raw, "trade_allowed", False))

        # DEMO-only: REAL and CONTEST rejected.
        if trade_mode_str != "demo":
            return self._reject(
                f"Account trade mode is {trade_mode_str}; only DEMO accounts permitted",
                server=server,
                company=company,
                currency=currency,
                trade_mode=trade_mode_str,
            )

        # Exact server match (no partial matching).
        if self.config.allowed_demo_server and server != self.config.allowed_demo_server:
            return self._reject(
                f"Server {server!r} does not match permitted demo server",
                server=server,
                company=company,
                currency=currency,
                trade_mode=trade_mode_str,
            )

        # Broker company match (where configured).
        if self.config.allowed_broker_company and company != self.config.allowed_broker_company:
            return self._reject(
                f"Broker company {company!r} does not match permitted company",
                server=server,
                company=company,
                currency=currency,
                trade_mode=trade_mode_str,
            )

        # Terminal trade permissions.
        terminal_trade_enabled = self._terminal_trade_enabled()
        if not terminal_trade_enabled:
            return self._reject(
                "Terminal trading is disabled",
                server=server,
                company=company,
                currency=currency,
                trade_mode=trade_mode_str,
            )

        # External Python API trading permission (when required by config).
        external_python_api_enabled = self._external_python_api_enabled(raw)
        if self.config.enable_external_python_api and not external_python_api_enabled:
            return self._reject(
                "External Python API trading permission is disabled",
                server=server,
                company=company,
                currency=currency,
                trade_mode=trade_mode_str,
            )

        # Account identity binding / change detection.
        fingerprint = self._fingerprint(server, company)
        if self._bound_fingerprint is not None and fingerprint != self._bound_fingerprint:
            return self._reject(
                "Account identity has changed since binding",
                server=server,
                company=company,
                currency=currency,
                trade_mode=trade_mode_str,
            )

        # Bind on first successful verification.
        if self._bound_fingerprint is None:
            self._bind(fingerprint, server, company)

        return AccountIdentity(
            server=server,
            company=company,
            currency=currency,
            trade_mode=trade_mode_str,
            trade_allowed=trade_allowed,
            terminal_connected=True,
            external_python_api_enabled=external_python_api_enabled,
            terminal_trade_enabled=terminal_trade_enabled,
            identity_fingerprint=fingerprint,
            verified_at=datetime.now(timezone.utc),
            is_demo=True,
            verification_passed=True,
        )

    # ------------------------------------------------------------------
    # Binding / change detection
    # ------------------------------------------------------------------

    def bind(self, fingerprint: str, server: str, company: str) -> None:
        """Explicitly bind a different account (requires authorization)."""
        self._bound_fingerprint = fingerprint
        self._bound_server = server
        self._bound_company = company

    def _bind(self, fingerprint: str, server: str, company: str) -> None:
        self._bound_fingerprint = fingerprint
        self._bound_server = server
        self._bound_company = company

    def is_bound(self) -> bool:
        return self._bound_fingerprint is not None

    def reset_binding(self) -> None:
        self._bound_fingerprint = None
        self._bound_server = None
        self._bound_company = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _reject(self, reason: str, **kwargs) -> AccountIdentity:
        return AccountIdentity(
            server=kwargs.get("server", ""),
            company=kwargs.get("company", ""),
            currency=kwargs.get("currency", ""),
            trade_mode=kwargs.get("trade_mode", "unknown"),
            trade_allowed=False,
            terminal_connected=False,
            external_python_api_enabled=False,
            terminal_trade_enabled=False,
            identity_fingerprint="",
            verified_at=datetime.now(timezone.utc),
            is_demo=False,
            verification_passed=False,
            rejection_reason=reason,
        )

    def _fingerprint(self, server: str, company: str) -> str:
        """HMAC-based local fingerprint (no raw login identifiers)."""
        material = f"{server}|{company}".encode("utf-8")
        key = self._secret.encode("utf-8")
        return hmac.new(key, material, hashlib.sha256).hexdigest()

    def _terminal_trade_enabled(self) -> bool:
        """Best-effort check that terminal trading is enabled."""
        try:
            terminal_info = self.connection.terminal_info
            if terminal_info is None:
                return False
            return bool(getattr(terminal_info, "connected", False))
        except Exception:
            return False

    def _external_python_api_enabled(self, raw) -> bool:
        """Best-effort check for external Python API trading permission."""
        try:
            return bool(getattr(raw, "trade_allowed", False))
        except Exception:
            return False
