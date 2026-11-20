"""MT5 terminal connection management."""

from __future__ import annotations

import glob
import logging
import os
from dataclasses import dataclass
from typing import Optional

from src.broker.mt5.exceptions import (
    MT5ConnectionError,
    MT5InitializationError,
    MT5NotInstalledError,
    MT5TerminalNotFoundError,
    MT5TerminalNotRunningError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MT5TerminalInfo:
    """Information about the connected MT5 terminal."""
    version: str
    build: int
    name: str
    company: str
    path: str
    connected: bool


class MT5ConnectionManager:
    """Manages MT5 terminal connection lifecycle.

    - Discovers MT5 terminal executable (including PU Prime installation)
    - Detects whether a terminal is already running before connecting
    - Connects to an already-running terminal (does not auto-launch new ones)
    - Initializes and shuts down MT5 API
    - Handles connection status and reconnection
    - Provides terminal version information
    - Reports exact IPC/initialization failure causes
    """

    # Terminal executable search paths. PU Prime paths are checked first so the
    # correct broker terminal is preferred when both generic and broker-specific
    # installations exist.
    TERMINAL_PATHS = [
        os.environ.get("MT5_TERMINAL_PATH"),
        r"C:\Program Files\PU Prime MT5 Terminal\terminal64.exe",
        r"C:\Program Files (x86)\PU Prime MT5 Terminal\terminal64.exe",
        r"C:\Program Files\MetaTrader 5\terminal64.exe",
        r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
    ]

    def __init__(
        self,
        terminal_path: Optional[str] = None,
        timeout: int = 30,
        portable: bool = False,
    ) -> None:
        """Initialize connection manager.

        Args:
            terminal_path: Optional explicit path to MT5 terminal executable.
                          If None, attempts auto-discovery.
            timeout: Connection timeout in seconds.
            portable: Whether to use portable mode (no registry lookup).
        """
        self._terminal_path = terminal_path
        self._timeout = timeout
        self._portable = portable
        self._initialized = False
        self._mt5_module = None
        self._terminal_info: Optional[MT5TerminalInfo] = None
        self._last_error: Optional[str] = None

    @property
    def is_initialized(self) -> bool:
        """Whether MT5 API is initialized."""
        return self._initialized

    @property
    def terminal_info(self) -> Optional[MT5TerminalInfo]:
        """Get terminal information if connected."""
        return self._terminal_info

    @property
    def last_error(self) -> Optional[str]:
        """Get last error message."""
        return self._last_error

    @property
    def terminal_path(self) -> Optional[str]:
        """Resolved terminal executable path."""
        return self._terminal_path

    def _import_mt5(self) -> None:
        """Import MetaTrader5 module, raising if not installed."""
        try:
            import MetaTrader5 as mt5
            self._mt5_module = mt5
        except ImportError as exc:
            raise MT5NotInstalledError(
                "MetaTrader5 Python package not installed. "
                "Install with: pip install MetaTrader5"
            ) from exc

    @staticmethod
    def detect_running_terminal() -> Optional[dict]:
        """Detect a running terminal64.exe process without terminating it.

        Returns a dict with pid/name/exe/username, or None if not running.
        """
        try:
            import psutil  # type: ignore
        except ImportError:
            return None

        for proc in psutil.process_iter(["pid", "name", "exe", "username"]):
            try:
                info = proc.info
                name = info.get("name") or ""
                if "terminal64" in name.lower():
                    return {
                        "pid": info.get("pid"),
                        "name": info.get("name"),
                        "exe": info.get("exe"),
                        "username": info.get("username"),
                    }
            except Exception:  # NoSuchProcess / AccessDenied / ZombieProcess
                continue
        return None

    def _discover_terminal(self) -> str:
        """Auto-discover MT5 terminal executable path.

        Returns the first existing path from the search list.
        """
        # Check environment variable first
        env_path = os.environ.get("MT5_TERMINAL_PATH")
        if env_path and os.path.isfile(env_path):
            return env_path

        # Check standard installation locations
        for path in self.TERMINAL_PATHS[1:]:
            if path and os.path.isfile(path):
                return path

        # Check AppData for portable installations
        appdata_pattern = r"%APPDATA%\MetaQuotes\Terminal\*\terminal64.exe"
        expanded = os.path.expandvars(appdata_pattern)
        matches = glob.glob(expanded)
        if matches:
            latest = max(matches, key=os.path.getmtime)
            if os.path.isfile(latest):
                return latest

        raise MT5TerminalNotFoundError(
            "Could not locate MT5 terminal executable. "
            "Set MT5_TERMINAL_PATH environment variable or install MT5 terminal."
        )

    def initialize(self) -> bool:
        """Initialize connection to MT5 terminal.

        Calls ``mt5.initialize(path=...)`` which connects to an already-running
        terminal or launches one at the configured path. Does NOT create
        duplicate terminal processes when one is already running.

        Returns:
            True if initialization successful.

        Raises:
            MT5NotInstalledError: If MetaTrader5 package not installed.
            MT5TerminalNotFoundError: If terminal executable not found.
            MT5InitializationError: If initialization fails (includes last_error).
        """
        if self._initialized:
            logger.warning("MT5 already initialized")
            return True

        self._import_mt5()
        mt5 = self._mt5_module

        # Discover terminal path if not provided
        if self._terminal_path is None:
            self._terminal_path = self._discover_terminal()
            logger.info("Auto-discovered MT5 terminal: %s", self._terminal_path)

        # Verify the terminal executable exists
        if not os.path.isfile(self._terminal_path):
            raise MT5TerminalNotFoundError(
                f"MT5 terminal executable not found: {self._terminal_path}"
            )

        # Log whether a terminal is already running (informational only;
        # mt5.initialize() will connect to it or launch a new one).
        running = self.detect_running_terminal()
        if running:
            logger.info(
                "Detected running MT5 terminal: pid=%s exe=%s",
                running.get("pid"),
                running.get("exe"),
            )
        else:
            logger.info(
                "No running MT5 terminal detected; mt5.initialize() will "
                "attempt to launch the terminal at %s.",
                self._terminal_path,
            )

        # Initialize MT5 against the terminal (launches if not running).
        logger.info("Initializing MT5 with terminal: %s", self._terminal_path)
        try:
            if self._portable:
                result = mt5.initialize(path=self._terminal_path, portable=True)
            else:
                result = mt5.initialize(path=self._terminal_path)
        except Exception as exc:
            raise MT5InitializationError(f"MT5 initialization exception: {exc}") from exc

        if not result:
            error_code, error_desc = mt5.last_error()
            self._last_error = f"({error_code}, {error_desc})"
            raise MT5InitializationError(
                f"MT5 initialization failed: {self._last_error}. "
                "Common causes: terminal not running or not logged in, "
                "wrong terminal path, process elevation mismatch, or IPC port "
                "conflict (port 22346). Open MetaTrader 5, log into your PU "
                "Prime DEMO account, and keep it running before connecting."
            )

        self._initialized = True
        self._update_terminal_info()
        logger.info("MT5 initialized successfully: %s", self._terminal_info)
        return True

    def _update_terminal_info(self) -> None:
        """Update terminal information from MT5."""
        mt5 = self._mt5_module
        if mt5 is None:
            return

        try:
            info = mt5.terminal_info()
            if info:
                self._terminal_info = MT5TerminalInfo(
                    version=getattr(info, 'version', 'unknown'),
                    build=getattr(info, 'build', 0),
                    name=getattr(info, 'name', 'MetaTrader 5'),
                    company=getattr(info, 'company', 'MetaQuotes'),
                    path=self._terminal_path or 'unknown',
                    connected=True,
                )
        except Exception as exc:
            logger.warning("Failed to get terminal info: %s", exc)

    def check_connection(self) -> bool:
        """Check if MT5 connection is alive."""
        if not self._initialized or self._mt5_module is None:
            return False

        try:
            info = self._mt5_module.terminal_info()
            if info is None:
                self._last_error = "Terminal info returned None"
                return False
            self._update_terminal_info()
            return True
        except Exception as exc:
            self._last_error = str(exc)
            return False

    def reconnect(self) -> bool:
        """Attempt to reconnect to MT5 terminal.

        Shuts down the current connection and re-initializes against a running
        terminal. Does not create duplicate terminal processes.
        """
        logger.info("Attempting MT5 reconnection...")
        self.shutdown()
        return self.initialize()

    def shutdown(self) -> bool:
        """Shutdown MT5 connection gracefully."""
        if not self._initialized or self._mt5_module is None:
            return True

        try:
            self._mt5_module.shutdown()
            logger.info("MT5 shutdown complete")
        except Exception as exc:
            logger.warning("Error during MT5 shutdown: %s", exc)
        finally:
            self._initialized = False
            self._terminal_info = None
            self._mt5_module = None

        return True

    def get_last_error(self) -> tuple[int, str]:
        """Get last MT5 error code and description."""
        if self._mt5_module is None:
            return (-1, "MT5 not initialized")
        return self._mt5_module.last_error()


class MT5AccountInfo:
    """MT5 account information for demo-only validation.

    Uses the official MT5 ``trade_mode`` enumeration:

    * ``ACCOUNT_TRADE_MODE_DEMO``    = 0  (accepted)
    * ``ACCOUNT_TRADE_MODE_CONTEST`` = 1  (rejected)
    * ``ACCOUNT_TRADE_MODE_REAL``    = 2  (rejected)

    The numeric values are defined locally so this module works even when the
    MetaTrader5 package exposes them under different names. When the package is
    importable, its own constants are preferred.
    """

    # Official MT5 trade-mode values (fallback; overridden from the package
    # when available).
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_CONTEST = 1
    ACCOUNT_TRADE_MODE_REAL = 2

    def __init__(self, mt5_module) -> None:
        self._mt5 = mt5_module
        # Prefer the package's own constants when present and genuinely int.
        self.ACCOUNT_TRADE_MODE_DEMO = self._resolve_constant(
            mt5_module, "ACCOUNT_TRADE_MODE_DEMO", 0
        )
        self.ACCOUNT_TRADE_MODE_CONTEST = self._resolve_constant(
            mt5_module, "ACCOUNT_TRADE_MODE_CONTEST", 1
        )
        self.ACCOUNT_TRADE_MODE_REAL = self._resolve_constant(
            mt5_module, "ACCOUNT_TRADE_MODE_REAL", 2
        )

    @staticmethod
    def _resolve_constant(mt5_module, name: str, fallback: int) -> int:
        """Return an int constant from the MT5 module, else the fallback."""
        value = getattr(mt5_module, name, None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        return fallback

    def get_account_info(self):
        """Get raw account info from MT5 (None when unavailable)."""
        return self._mt5.account_info()

    def is_account_available(self) -> bool:
        """Return True only when account information is present."""
        return self.get_account_info() is not None

    def _trade_mode(self):
        """Return the raw trade_mode value, or None when unavailable."""
        info = self.get_account_info()
        if info is None:
            return None
        return getattr(info, "trade_mode", None)

    def is_demo_account(self) -> bool:
        """Check if the connected account is a demo account."""
        return self._trade_mode() == self.ACCOUNT_TRADE_MODE_DEMO

    def is_contest_account(self) -> bool:
        """Check if the connected account is a contest account."""
        return self._trade_mode() == self.ACCOUNT_TRADE_MODE_CONTEST

    def is_real_account(self) -> bool:
        """Check if the connected account is a real/live account."""
        return self._trade_mode() == self.ACCOUNT_TRADE_MODE_REAL

    def get_account_mode_str(self) -> str:
        """Get human-readable account mode (demo | contest | real | unknown)."""
        mode = self._trade_mode()
        if mode == self.ACCOUNT_TRADE_MODE_DEMO:
            return "demo"
        if mode == self.ACCOUNT_TRADE_MODE_CONTEST:
            return "contest"
        if mode == self.ACCOUNT_TRADE_MODE_REAL:
            return "real"
        if mode is None:
            return "unknown"
        return f"unknown({mode})"

    def get_safe_account_summary(self) -> dict:
        """Get account summary without sensitive data."""
        info = self.get_account_info()
        if info is None:
            return {"mode": "unknown", "connected": False}

        return {
            "mode": self.get_account_mode_str(),
            "server": getattr(info, 'server', 'unknown'),
            "currency": getattr(info, 'currency', 'unknown'),
            "connected": True,
        }
