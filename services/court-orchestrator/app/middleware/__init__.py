"""The service middleware chain, installed strictly in order:

1. env_loader — load + validate all environment variables before launch
2. cors      — enable cross-origin access
3. datacat   — console logger: init banner + per-request log lines
4. preflight — verify 1-3 are installed before serving
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from fastapi import FastAPI

from . import cors, datacat, env_loader, preflight


def install_all(
    app: FastAPI,
    service_name: str,
    cors_origins: List[str],
    banner_extra: Optional[Callable[[], Dict[str, str]]] = None,
) -> None:
    app.state.middleware_installed = {}
    env_loader.install(app)
    cors.install(app, origins=cors_origins)
    datacat.install(app, service_name=service_name, banner_extra=banner_extra)
    preflight.install(app)
