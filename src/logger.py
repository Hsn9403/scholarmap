#!/usr/bin/env python3
"""Logging configuration for the project."""
from __future__ import annotations
import logging
import sys
from typing import Optional


def setup_logger(name: str = "sci_diligence", level: int = logging.INFO) -> logging.Logger:
    """
    Configure and return a logger instance.

    Args:
        name: Logger name
        level: Logging level (default: INFO)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Console handler with formatting
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter = logging.Formatter(
        fmt='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    return logger


# Default logger instance
logger = setup_logger()


def log_api_call(endpoint: str, params: Optional[dict] = None) -> None:
    """Log an API call for debugging."""
    logger.debug(f"API call to {endpoint}")
    if params:
        logger.debug(f"  Params: {params}")


def log_error(error: Exception, context: str = "") -> None:
    """Log an error with context."""
    if context:
        logger.error(f"{context}: {type(error).__name__}: {error}")
    else:
        logger.error(f"{type(error).__name__}: {error}")
