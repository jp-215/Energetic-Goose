"""Middleware 3/4 — datacat logger.

Console logging for the whole service: an initialization banner announcing
the app on the terminal when it launches, plus a per-request log line
(method, path, status, duration).
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Dict, Optional

from fastapi import FastAPI, Request

logger = logging.getLogger("datacat")

_FORMAT = "%(asctime)s | datacat | %(levelname)s | %(message)s"


def _ensure_handler() -> None:
    logger.setLevel(logging.INFO)
    logger.propagate = True  # let pytest caplog / root handlers see records too
    if any(getattr(h, "_datacat", False) for h in logger.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler._datacat = True  # type: ignore[attr-defined]
    logger.addHandler(handler)


def install(
    app: FastAPI,
    service_name: str,
    banner_extra: Optional[Callable[[], Dict[str, str]]] = None,
) -> None:
    _ensure_handler()

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "%s %s -> %s (%d ms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response

    async def announce() -> None:
        logger.info("=" * 56)
        logger.info("%s launched", service_name)
        for key, value in (banner_extra() if banner_extra else {}).items():
            logger.info("  %s: %s", key, value)
        installed = ", ".join(k for k, v in app.state.middleware_installed.items() if v)
        logger.info("  middleware chain: %s", installed)
        logger.info("=" * 56)

    app.router.on_startup.append(announce)
    app.state.middleware_installed["datacat"] = True
