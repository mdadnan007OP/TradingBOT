"""Phase 9 execution gateway dispatch.

Routes execution requests to the configured adapter based on execution mode.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.execution.config import ExecutionConfig, ExecutionMode
from src.execution.interfaces import ExecutionGateway
from src.execution.models import ExecutionRequest, ExecutionResult

logger = logging.getLogger(__name__)


class ExecutionGatewayRouter:
    """Selects the active execution gateway for a given mode."""

    def __init__(self, gateways: Dict[str, ExecutionGateway]) -> None:
        self._gateways = gateways

    def gateway_for_mode(self, mode: str) -> Optional[ExecutionGateway]:
        return self._gateways.get(mode)

    def can_submit(self, mode: str) -> bool:
        gw = self._gateways.get(mode)
        return gw is not None and gw.can_submit_orders()
