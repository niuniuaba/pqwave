#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Logging configuration for pqwave.

This module provides logging setup utilities for the pqwave application.
It configures loggers based on command-line arguments to control output verbosity.
"""

import logging
import sys
from typing import Optional


def setup_logging(
    debug: bool = False,
    verbose: bool = False,
    quiet: bool = False,
    log_file: Optional[str] = None
) -> logging.Logger:
    """Configure logging based on command-line arguments

    Args:
        debug: Enable debug-level logging (most verbose)
        verbose: Enable info-level logging (user feedback)
        quiet: Suppress all output except errors
        log_file: Optional file path to write logs to

    Returns:
        Configured logger instance
    """

    # Determine logging level based on arguments
    # Priority: debug > verbose > default (WARNING) > quiet (ERROR)
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    elif quiet:
        level = logging.ERROR
    else:
        level = logging.WARNING

    # Configure root logger for pqwave
    logger = logging.getLogger('pqwave')
    logger.setLevel(level)

    # Clear any existing handlers to avoid duplicate output
    logger.handlers.clear()

    # Console handler for stdout
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Format for console output
    # Simple format: LEVEL: message
    console_format = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler if log file specified
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(level)

            # More detailed format for file logs
            file_format = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(file_format)
            logger.addHandler(file_handler)

            logger.info(f"Logging to file: {log_file}")
        except Exception as e:
            logger.error(f"Failed to create log file {log_file}: {e}")

    # Log the current logging level
    level_names = {
        logging.DEBUG: 'DEBUG',
        logging.INFO: 'INFO',
        logging.WARNING: 'WARNING',
        logging.ERROR: 'ERROR'
    }
    logger.debug(f"Logging level set to: {level_names.get(level, level)}")

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a specific module

    Args:
        name: Module name (usually __name__)

    Returns:
        Logger instance configured for the module
    """
    # Remove 'pqwave.' prefix if present to keep logger names consistent
    if name.startswith('pqwave.'):
        name = name[7:]  # Remove 'pqwave.' prefix

    return logging.getLogger(f'pqwave.{name}')