"""Diagnostics package for the Forex trading bot.

Import diagnostics lazily to avoid double-execution warnings when run via
``python -m src.diagnostics.mt5_diagnostics``.
"""

__all__ = ["run_diagnostics"]


def __getattr__(name: str):
    if name == "run_diagnostics":
        from src.diagnostics.mt5_diagnostics import run_diagnostics
        return run_diagnostics
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")