from __future__ import annotations

import logging
import sys
from typing import Any

from rich.logging import RichHandler


def setup_logging(level: int = logging.INFO) -> None:
    """Configure structured logging using Rich."""
    from rich.console import Console
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=Console(stderr=True), rich_tracebacks=True, markup=True)]
    )


def get_logger(name: str) -> logging.Logger:
    """Get a named logger."""
    return logging.getLogger(name)


class AtlasLogger:
    """Wrapper for standardized logging across the project."""
    
    def __init__(self, name: str):
        self.logger = get_logger(name)
        
    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self.logger.info(msg, *args, **kwargs)
        
    def warn(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self.logger.warning(msg, *args, **kwargs)
        
    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self.logger.error(msg, *args, **kwargs)
        
    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self.logger.debug(msg, *args, **kwargs)
