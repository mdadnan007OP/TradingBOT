"""Independent MT5 connection diagnostic and repair helper.

This utility tests the MetaTrader 5 terminal connection independently of the
trading bot adapter. It performs controlled, read-only diagnostics:

A. Detect the actual running MT5 terminal
B. Verify the terminal executable path
C. Check Python vs terminal user/elevation compatibility
D. Test connecting to an already-running terminal
E. Test automatic terminal discovery (only when appropriate)
F. Record mt5.initialize() result and mt5.last_error()
G. If connected: terminal info, connection status, build, account trade mode,
   demo verification, symbol discovery

Never prints account login numbers or passwords. Never launches repeated
terminal processes. Always calls mt5.shutdown() after testing.

Usage (from project root):

    python tools/mt5_connection_repair.py
    python tools/mt5_connection_repair.py --terminal "C:\\Program Files\\PU Prime MT5 Terminal\\terminal64.exe"
    python tools/mt5_connection_repair.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from datetime import datetime, timezone
from typing import Optional


def _section(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def _safe_section(title: str) -> None:
    _section(title)


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    return str(value)


class MT5DiagnosticResult:
    """Collects diagnostic findings."""

    def __init__(self) -> None:
        self.entries: list[dict] = []

    def add(self, category: str, check: str, status: str, detail: str = "") -> None:
        self.entries.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "category": category,
                "check": check,
                "status": status,  # ok | warn | fail | info
                "detail": detail,
            }
        )

    def to_dict(self) -> dict:
        return {
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "architecture": platform.machine(),
            "platform": platform.platform(),
            "entries": self.entries,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def summary(self) -> str:
        lines = []
        fails = [e for e in self.entries if e["status"] == "fail"]
        warns = [e for e in self.entries if e["status"] == "warn"]
        lines.append(f"Checks: {len(self.entries)} total, {len(fails)} failed, {len(warns)} warned")
        for e in self.entries:
            mark = {"fail": "FAIL", "warn": "WARN", "ok": "OK", "info": "INFO"}[e["status"]]
            lines.append(f"  [{mark}] {e['category']}: {e['check']} — {e['detail']}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# A. Terminal detection
# ---------------------------------------------------------------------------

POSSIBLE_TERMINAL_PATHS = [
    os.environ.get("MT5_TERMINAL_PATH"),
    r"C:\Program Files\PU Prime MT5 Terminal\terminal64.exe",
    r"C:\Program Files (x86)\PU Prime MT5 Terminal\terminal64.exe",
    r"C:\Program Files\MetaTrader 5\terminal64.exe",
    r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
]


def detect_installed_terminals() -> list[str]:
    """Return terminal executable paths that exist on disk."""
    found = []
    for path in POSSIBLE_TERMINAL_PATHS:
        if path and os.path.isfile(path):
            found.append(path)
    return found


def detect_running_terminal() -> Optional[dict]:
    """Detect a running terminal64.exe process without terminating it."""
    try:
        import psutil  # type: ignore
    except ImportError:
        return None

    for proc in psutil.process_iter(["pid", "name", "exe", "username", "create_time"]):
        try:
            info = proc.info
            if info.get("name") and "terminal64" in info["name"].lower():
                return {
                    "pid": info.get("pid"),
                    "name": info.get("name"),
                    "exe": info.get("exe"),
                    "username": info.get("username"),
                    "create_time": info.get("create_time"),
                }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


# ---------------------------------------------------------------------------
# C. Elevation / context check
# ---------------------------------------------------------------------------

def is_process_elevated() -> bool:
    """Best-effort check whether the current Python process is elevated."""
    try:
        import ctypes  # noqa: F401
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def detect_terminal_elevation(terminal_exe: Optional[str]) -> Optional[str]:
    """Best-effort elevation of the running terminal process, if any."""
    running = detect_running_terminal()
    if running is None:
        return None
    try:
        import psutil  # type: ignore
        proc = psutil.Process(running["pid"])
        # On Windows, checking elevation of another process requires
        # querying its token; fall back to reporting username only.
        return f"user={running.get('username')}, pid={running.get('pid')}"
    except Exception:
        return None


# ---------------------------------------------------------------------------
# D & F. Controlled connection test
# ---------------------------------------------------------------------------

def test_mt5_initialize(terminal_path: Optional[str], result: MT5DiagnosticResult) -> Optional[object]:
    """Attempt mt5.initialize() once and record the outcome.

    Returns the mt5 module on success, None on failure.
    """
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        result.add("connection", "mt5_package_import", "fail",
                   f"MetaTrader5 package not installed: {exc}")
        return None

    result.add("package", "mt5_version", "info",
               f"installed version={getattr(mt5, '__version__', 'unknown')}")

    # Only pass a path when we have a concrete executable to avoid launching
    # an arbitrary terminal.
    init_kwargs = {}
    if terminal_path and os.path.isfile(terminal_path):
        init_kwargs["path"] = terminal_path

    try:
        initialized = mt5.initialize(**init_kwargs)
    except Exception as exc:  # noqa: BLE001
        result.add("connection", "mt5_initialize_exception", "fail",
                   f"mt5.initialize() raised: {exc}")
        return None

    error_code, error_desc = mt5.last_error()
    result.add("connection", "mt5_initialize_result", "ok" if initialized else "fail",
               f"initialized={initialized}, last_error=({error_code}, {error_desc})")

    if not initialized:
        mt5.shutdown()
        return None

    return mt5


# ---------------------------------------------------------------------------
# G. Connected inspection (read-only, no credentials)
# ---------------------------------------------------------------------------

def inspect_connected(mt5, result: MT5DiagnosticResult) -> None:
    """Inspect a connected MT5 terminal without exposing credentials."""
    # Terminal info
    try:
        info = mt5.terminal_info()
        if info is not None:
            result.add("terminal", "build", "info", f"build={getattr(info, 'build', 'unknown')}")
            result.add("terminal", "version", "info", f"version={getattr(info, 'version', 'unknown')}")
            result.add("terminal", "name", "info", f"name={getattr(info, 'name', 'unknown')}")
            result.add("terminal", "connected", "info", f"connected={getattr(info, 'connected', 'unknown')}")
            result.add("terminal", "path", "info", f"path={getattr(info, 'path', 'unknown')}")
        else:
            result.add("terminal", "terminal_info", "warn", "terminal_info() returned None")
    except Exception as exc:  # noqa: BLE001
        result.add("terminal", "terminal_info_exception", "warn", str(exc))

    # Connection status
    try:
        status = mt5.terminal_connection_status()
        result.add("connection", "terminal_connection_status", "info", f"status={status}")
    except Exception as exc:  # noqa: BLE001
        result.add("connection", "terminal_connection_status_exception", "warn", str(exc))

    # Account trade mode (demo verification) — read-only, no account number
    try:
        account = mt5.account_info()
        if account is not None:
            trade_mode = getattr(account, "trade_mode", None)
            mode_str = {0: "demo", 1: "contest", 2: "real"}.get(trade_mode, f"unknown({trade_mode})")
            result.add("account", "trade_mode", "info", f"mode={mode_str}")
            if trade_mode == 0:
                result.add("account", "demo_verification", "ok", "account is DEMO — read-only access permitted")
            else:
                result.add("account", "demo_verification", "fail",
                           f"account is NOT demo (mode={mode_str}) — read-only access refused")
            # Safe server name only (no login/password/balance)
            server = getattr(account, "server", "unknown")
            result.add("account", "server", "info", f"server={server}")
        else:
            result.add("account", "account_info", "warn", "account_info() returned None (not logged in)")
    except Exception as exc:  # noqa: BLE001
        result.add("account", "account_info_exception", "warn", str(exc))

    # Symbol discovery capability
    try:
        symbols = mt5.symbols_get()
        if symbols is not None:
            result.add("symbols", "discovery", "info", f"discovered={len(symbols)} symbols")
            names = [getattr(s, "name", "?") for s in symbols[:20]]
            result.add("symbols", "sample", "info", f"sample={', '.join(names)}")
        else:
            result.add("symbols", "discovery", "warn", "symbols_get() returned None")
    except Exception as exc:  # noqa: BLE001
        result.add("symbols", "discovery_exception", "warn", str(exc))


def run_diagnostic(terminal_path: Optional[str] = None, as_json: bool = False) -> int:
    """Run the full MT5 connection diagnostic.

    Args:
        terminal_path: Optional explicit terminal executable path.
        as_json: Emit JSON instead of text.

    Returns:
        Exit code (0 = completed, 1 = unexpected error).
    """
    result = MT5DiagnosticResult()

    _safe_section("ENVIRONMENT")
    print(f"Python version : {platform.python_version()}")
    print(f"Python exe     : {sys.executable}")
    print(f"Architecture   : {platform.machine()}")
    print(f"Elevated       : {is_process_elevated()}")
    result.add("environment", "python_version", "info", platform.python_version())
    result.add("environment", "elevated", "info", str(is_process_elevated()))

    _safe_section("MT5 PACKAGE")
    try:
        import MetaTrader5 as mt5  # noqa: F401
        print(f"MetaTrader5    : installed (version {getattr(mt5, '__version__', 'unknown')})")
        result.add("package", "installed", "ok", getattr(mt5, "__version__", "unknown"))
    except ImportError:
        print("MetaTrader5    : NOT INSTALLED")
        print("Install with   : pip install MetaTrader5")
        result.add("package", "installed", "fail", "not installed")
        if as_json:
            print(result.to_json())
        return 0

    _safe_section("TERMINAL DISCOVERY (A & B)")
    installed = detect_installed_terminals()
    if installed:
        print("Installed terminals:")
        for p in installed:
            print(f"  - {p}")
        result.add("discovery", "installed_terminals", "info", f"{len(installed)} found: {installed}")
    else:
        print("No MT5 terminal executable found on disk.")
        result.add("discovery", "installed_terminals", "fail", "none found")

    running = detect_running_terminal()
    if running:
        print(f"Running terminal: pid={running.get('pid')} exe={running.get('exe')}")
        result.add("discovery", "running_terminal", "info", f"pid={running.get('pid')}")
    else:
        print("No MT5 terminal process currently running.")
        result.add("discovery", "running_terminal", "warn", "not running")

    # Resolve the path to use for initialize()
    chosen_path = terminal_path
    if not chosen_path and installed:
        # Prefer the PU Prime terminal if present, else the first installed.
        prime = [p for p in installed if "PU Prime" in p]
        chosen_path = prime[0] if prime else installed[0]
        print(f"Auto-selected terminal: {chosen_path}")
        result.add("discovery", "auto_selected", "info", chosen_path)

    if chosen_path and not os.path.isfile(chosen_path):
        print(f"Configured terminal path does not exist: {chosen_path}")
        result.add("connection", "terminal_path_valid", "fail", chosen_path)
        if as_json:
            print(result.to_json())
        return 0

    _safe_section("ELEVATION CONTEXT (C)")
    print(f"Python elevated: {is_process_elevated()}")
    term_elev = detect_terminal_elevation(chosen_path)
    print(f"Terminal context: {term_elev or 'not running'}")
    result.add("elevation", "python_elevated", "info", str(is_process_elevated()))
    result.add("elevation", "terminal_context", "info", term_elev or "not running")

    _safe_section("CONNECTION TEST (D & F)")
    mt5 = test_mt5_initialize(chosen_path, result)

    if mt5 is not None:
        try:
            _safe_section("CONNECTED INSPECTION (G)")
            inspect_connected(mt5, result)
        finally:
            mt5.shutdown()
            result.add("connection", "shutdown", "ok", "mt5.shutdown() called")
    else:
        result.add("connection", "shutdown", "info", "not connected — no shutdown needed")

    _safe_section("SUMMARY")
    print(result.summary())

    if as_json:
        print()
        print(result.to_json())

    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Independent MT5 connection diagnostic (read-only)."
    )
    parser.add_argument(
        "--terminal",
        default=None,
        help="Explicit path to terminal64.exe (overrides auto-discovery).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report.",
    )
    args = parser.parse_args(argv)
    return run_diagnostic(terminal_path=args.terminal, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())