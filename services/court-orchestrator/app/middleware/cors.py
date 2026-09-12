"""Middleware 2/4 — CORS.

Enables cross-origin access. The orchestrator is an internal service (only
the gateway calls it), so its default origin list is empty — but the slot
still installs so every service carries the same four-middleware chain.
"""

from __future__ import annotations

from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def install(app: FastAPI, origins: List[str]) -> None:
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.state.middleware_installed["cors"] = True
    app.state.cors_origins = origins
