"""Application logging setup.

Provides a single ``setup_logging`` function that configures the root logger
with console output and (optionally) rotating file output under the configured
log directory. All modules should obtain loggers via ``logging.getLogger(__name__)``.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from typing import Optional

from src.config import CONFIG


def setup_logging(level: Optional[str] = None, log_dir: Optional[str] = None) -> logging.Logger:
    """Configure and return the root application logger.

    Args:
        level: Logging level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            Defaults to the configured value.
        log_dir: Directory for log files. Defaults to the configured value.
            If empty or None, file logging is disabled.

    Returns:
        The configured root logger.
    """
    level_name = (level or CONFIG.logging.level).upper()
    log_level = getattr(logging, level_name, logging.INFO)

    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Avoid duplicate handlers if called more than once.
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler (always on).
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Optional rotating file handler.
    if log_dir or CONFIG.logging.dir:
        target_dir = log_dir or CONFIG.logging.dir
        try:
            os.makedirs(target_dir, exist_ok=True)
            log_path = os.path.join(target_dir, "trading_bot.log")
            file_handler = logging.handlers.RotatingFileHandler(
                log_path, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError as exc:
            # File logging is a convenience, not a requirement. Fail safely.
            logger.warning("Could not initialize file logging: %s", exc)

    logger.info("Logging initialized (level=%s)", level_name)
    return logger
