"""Phase 9 execution policy.

Mode gating: PAPER is the default and permanent safe mode. DEMO_AUTO requires
both environment enablement and a CLI activation flag. LIVE/REAL is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.execution.config import ExecutionConfig, ExecutionMode


@dataclass
class PolicyDecision:
    permitted: bool
    mode: str
    reason: str
    requires_manual_approval: bool
    automatic_permitted: bool


class ExecutionPolicy:
    """Enforces execution-mode safety policy."""

    def __init__(self, config: ExecutionConfig, cli_demo_auto: bool = False) -> None:
        self.config = config
        self.cli_demo_auto = cli_demo_auto

    def decide(self) -> PolicyDecision:
        mode = self.config.mode

        if mode == ExecutionMode.PAPER:
            return PolicyDecision(
                permitted=True,
                mode="PAPER",
                reason="Paper mode: simulated execution only, no broker calls.",
                requires_manual_approval=False,
                automatic_permitted=False,
            )

        if mode == ExecutionMode.DEMO_MANUAL:
            if not self.config.demo_execution_enabled:
                return PolicyDecision(
                    permitted=False,
                    mode="DEMO_MANUAL",
                    reason="DEMO_MANUAL requires DEMO_EXECUTION_ENABLED=true.",
                    requires_manual_approval=True,
                    automatic_permitted=False,
                )
            return PolicyDecision(
                permitted=True,
                mode="DEMO_MANUAL",
                reason="Demo manual mode: per-order user approval required.",
                requires_manual_approval=True,
                automatic_permitted=False,
            )

        if mode == ExecutionMode.DEMO_AUTO:
            env_ok = self.config.demo_automatic_enabled
            cli_ok = self.cli_demo_auto
            if not env_ok:
                return PolicyDecision(
                    permitted=False,
                    mode="DEMO_AUTO",
                    reason="DEMO_AUTO requires DEMO_AUTOMATIC_ENABLED=true.",
                    requires_manual_approval=True,
                    automatic_permitted=False,
                )
            if not cli_ok:
                return PolicyDecision(
                    permitted=False,
                    mode="DEMO_AUTO",
                    reason="DEMO_AUTO requires explicit CLI activation flag.",
                    requires_manual_approval=True,
                    automatic_permitted=False,
                )
            if not self.config.demo_execution_enabled:
                return PolicyDecision(
                    permitted=False,
                    mode="DEMO_AUTO",
                    reason="DEMO_AUTO requires DEMO_EXECUTION_ENABLED=true.",
                    requires_manual_approval=True,
                    automatic_permitted=False,
                )
            return PolicyDecision(
                permitted=True,
                mode="DEMO_AUTO",
                reason="Demo automatic mode: gated by env + CLI activation.",
                requires_manual_approval=False,
                automatic_permitted=True,
            )

        # Any unknown or LIVE/REAL mode -> reject.
        return PolicyDecision(
            permitted=False,
            mode=str(mode),
            reason=f"Execution mode {mode} is not permitted.",
            requires_manual_approval=True,
            automatic_permitted=False,
        )

    def is_paper_default(self) -> bool:
        return self.config.mode == ExecutionMode.PAPER

    def live_trading_locked(self) -> bool:
        # LIVE mode does not exist; live trading is permanently unavailable.
        return True
