"""Phase 10 — Read-only monitoring dashboard.

A lightweight, localhost-only HTTP dashboard using the Python standard library
(http.server). It is READ-ONLY: no order submission controls, no sensitive
account identifiers, no passwords or secrets.

Default binding: 127.0.0.1 (localhost only).
"""

from __future__ import annotations

import html
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


def _escape(value: Any) -> str:
    """HTML-escape a value for safe display."""
    return html.escape(str(value))


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the read-only monitoring dashboard."""

    # Callbacks injected by the dashboard server.
    get_health: Optional[Callable[[], Dict[str, Any]]] = None
    get_status: Optional[Callable[[], Dict[str, Any]]] = None
    get_execution_summary: Optional[Callable[[], Dict[str, Any]]] = None

    # Suppress default request logging to stderr.
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        logger.debug("Dashboard request: %s", format % args)

    def _send_json(self, data: Dict[str, Any], status: int = 200) -> None:
        body = json.dumps(data, default=str, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body: str, status: int = 200) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]

        if path == "/" or path == "":
            self._send_html(self._dashboard_html())
        elif path == "/api/health":
            data = self.get_health() if self.get_health else {"error": "not available"}
            self._send_json(data)
        elif path == "/api/status":
            data = self.get_status() if self.get_status else {"error": "not available"}
            self._send_json(data)
        elif path == "/api/execution":
            data = (
                self.get_execution_summary()
                if self.get_execution_summary
                else {"error": "not available"}
            )
            self._send_json(data)
        else:
            self._send_json({"error": "not found"}, status=404)

    def _dashboard_html(self) -> str:
        """Render a simple read-only dashboard HTML page."""
        health = self.get_health() if self.get_health else {}
        status = self.get_status() if self.get_status else {}
        execution = self.get_execution_summary() if self.get_execution_summary else {}

        subsystems = health.get("subsystems", {}) if isinstance(health, dict) else {}

        rows = ""
        for name, sub in subsystems.items():
            rows += (
                f"<tr>"
                f"<td>{_escape(name)}</td>"
                f"<td>{_escape(sub.get('status', 'unknown'))}</td>"
                f"<td>{_escape(sub.get('detail', ''))}</td>"
                f"<td>{_escape(sub.get('latency_ms', '-'))} ms</td>"
                f"</tr>"
            )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Forex Trading Bot - Monitoring Dashboard</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; margin: 2rem; background: #f5f5f5; }}
  h1 {{ color: #1a1a2e; }}
  .card {{ background: white; border-radius: 8px; padding: 1.5rem; margin-bottom: 1rem; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
  .card h2 {{ margin-top: 0; color: #16213e; font-size: 1.1rem; border-bottom: 1px solid #e0e0e0; padding-bottom: 0.5rem; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
  th, td {{ text-align: left; padding: 0.5rem; border-bottom: 1px solid #e0e0e0; }}
  th {{ color: #666; font-size: 0.8rem; text-transform: uppercase; }}
  .status-healthy {{ color: #2e7d32; font-weight: bold; }}
  .status-degraded {{ color: #f57c00; font-weight: bold; }}
  .status-unhealthy {{ color: #c62828; font-weight: bold; }}
  .status-unknown {{ color: #9e9e9e; font-weight: bold; }}
  .muted {{ color: #666; font-size: 0.85rem; }}
  .badge {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: bold; }}
  .badge-paper {{ background: #e3f2fd; color: #1565c0; }}
  .badge-demo {{ background: #fff3e0; color: #e65100; }}
</style>
</head>
<body>
  <h1>Forex Trading Bot — Monitoring Dashboard</h1>
  <p class="muted">Read-only dashboard. No order submission. Binding: localhost only.</p>

  <div class="card">
    <h2>Overview</h2>
    <table>
      <tr><th>Application State</th><td>{_escape(status.get('state', 'unknown'))}</td></tr>
      <tr><th>Execution Mode</th><td>
        <span class="badge badge-{'demo' if 'demo' in str(status.get('mode','')).lower() else 'paper'}">
          {_escape(status.get('mode', 'unknown'))}
        </span>
      </td></tr>
      <tr><th>Uptime (seconds)</th><td>{_escape(status.get('uptime_seconds', '-'))}</td></tr>
      <tr><th>All Components Healthy</th><td>{_escape(status.get('all_components_healthy', '-'))}</td></tr>
      <tr><th>Critical Failures</th><td>{_escape(len(status.get('critical_failures', [])))}</td></tr>
    </table>
  </div>

  <div class="card">
    <h2>System Health</h2>
    <table>
      <tr><th>Subsystem</th><th>Status</th><th>Detail</th><th>Latency (ms)</th></tr>
      {rows or '<tr><td colspan="4">No subsystem health data available.</td></tr>'}
    </table>
  </div>

  <div class="card">
    <h2>Execution Monitoring</h2>
    <table>
      <tr><th>Metric</th><th>Value</th></tr>
      <tr><th>Total Executions</th><td>{_escape(execution.get('total_executions', '-'))}</td></tr>
      <tr><th>Unresolved</th><td>{_escape(execution.get('unresolved', '-'))}</td></tr>
      <tr><th>Reconciliation Status</th><td>{_escape(execution.get('reconciliation_status', '-'))}</td></tr>
    </table>
  </div>

  <div class="card">
    <h2>API Endpoints</h2>
    <ul>
      <li><code>GET /api/health</code> — System health JSON</li>
      <li><code>GET /api/status</code> — Application status JSON</li>
      <li><code>GET /api/execution</code> — Execution summary JSON</li>
    </ul>
    <p class="muted">This dashboard is read-only. It does not submit, modify, or cancel any orders.</p>
  </div>
</body>
</html>"""


class DashboardServer:
    """Read-only HTTP dashboard server bound to localhost by default."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        get_health: Optional[Callable[[], Dict[str, Any]]] = None,
        get_status: Optional[Callable[[], Dict[str, Any]]] = None,
        get_execution_summary: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> None:
        # Enforce localhost-only binding.
        if host not in ("127.0.0.1", "localhost", "::1"):
            logger.warning(
                "Dashboard host %s is not localhost; forcing 127.0.0.1 for security", host
            )
            host = "127.0.0.1"

        self.host = host
        self.port = port
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[Any] = None

        # Inject callbacks into handler class.
        DashboardHandler.get_health = get_health
        DashboardHandler.get_status = get_status
        DashboardHandler.get_execution_summary = get_execution_summary

    def start(self) -> bool:
        """Start the dashboard server. Returns True if started successfully."""
        try:
            self._server = ThreadingHTTPServer((self.host, self.port), DashboardHandler)
            import threading

            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            logger.info("Monitoring dashboard started on http://%s:%d", self.host, self.port)
            return True
        except OSError as exc:
            logger.exception("Failed to start dashboard on %s:%d: %s", self.host, self.port, exc)
            return False

    def stop(self) -> None:
        """Stop the dashboard server."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            logger.info("Monitoring dashboard stopped")

    def is_running(self) -> bool:
        return self._server is not None
