from __future__ import annotations

import logging
import os
import sys
from typing import Optional

try:
    from colorlog import ColoredFormatter
except Exception:  # pragma: no cover
    ColoredFormatter = None  # type: ignore

try:
    import structlog
except Exception:  # pragma: no cover
    structlog = None  # type: ignore


_LOG_FORMAT = (
    "%(log_color)s%(levelname)-8s%(reset)s " "%(blue)s%(name)s%(reset)s: %(message)s"
)

_LOG_COLORS = {
    "DEBUG": "cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
}


def _detect_production() -> bool:
    """Best-effort environment detection.

    Set one of these to switch to structlog JSON:
      - APP_ENV=production
      - ENV=production
      - PYTHON_ENV=production
    """
    val = (
        (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "")
        .strip()
        .lower()
    )
    return val in {"prod", "production"}


def configure_logging(
    *,
    level: int = logging.INFO,
    force: bool = False,
    production: Optional[bool] = None,
) -> None:
    """Configure global logging (call once at process startup).

    - Local/dev: colorlog pretty output (if installed).
    - Production: structlog JSON (if installed), else stdlib formatting.

    Args:
        level: Root logger level.
        force: Reconfigure even if handlers already exist.
        production: Override environment detection.
    """
    root = logging.getLogger()

    if root.handlers and not force:
        return

    # Clear existing handlers so we don't double-log.
    root.handlers.clear()

    is_prod = _detect_production() if production is None else production

    # --- Production: structlog JSON ---
    if is_prod and structlog is not None:
        # Stdlib handler (structlog renders into the message)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)
        root.setLevel(level)

        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(level),
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        return

    # --- Local/dev: colorlog (fallback to stdlib if missing) ---
    handler = logging.StreamHandler(sys.stdout)

    if ColoredFormatter is not None:
        handler.setFormatter(
            ColoredFormatter(
                _LOG_FORMAT,
                log_colors=_LOG_COLORS,
            )
        )
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: Optional[str] = None):
    """Get a logger with consistent behavior.

    If structlog is configured (prod), returns a BoundLogger.
    Otherwise returns a stdlib Logger.
    """
    if structlog is not None:
        try:
            return structlog.get_logger(name)
        except Exception:
            pass
    return logging.getLogger(name)
