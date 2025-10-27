"""
Guaraci Logging System
=====================

Centralized logging configuration using loguru for better performance and features.
"""

import sys
from pathlib import Path
from loguru import logger
from guaraci.core.config import config


def setup_logging():
    """Configure logging for Guaraci."""
    # Remove default handler
    logger.remove()

    # Console handler with rich formatting
    logger.add(
        sys.stderr,
        level=config.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # File handler if specified
    if config.log_file:
        logger.add(
            config.log_file,
            level="DEBUG",
            format=(
                "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
                "{name}:{function}:{line} | {message}"
            ),
            rotation="10 MB",
            retention="30 days",
            compression="gz",
            backtrace=True,
            diagnose=True,
        )

    return logger


if __name__ == "__main__":
    setup_logging()
    logger.info("Logging initialized (manual test mode)")
