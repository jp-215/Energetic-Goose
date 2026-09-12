"""Middleware 4/4 — preflight.

Prerequisite guard: verifies the first three middlewares (env_loader, cors,
datacat) actually installed before the app is allowed to serve. Runs last in
the chain; a missing prerequisite aborts launch.
"""

from __future__ import annotations

from fastapi import FastAPI

PREREQUISITES = ("env_loader", "cors", "datacat")


def install(app: FastAPI) -> None:
    installed = getattr(app.state, "middleware_installed", {})
    missing = [name for name in PREREQUISITES if not installed.get(name)]
    if missing:
        raise RuntimeError(
            f"preflight: prerequisite middleware not installed: {missing}. "
            "Refusing to launch."
        )
    app.state.middleware_installed["preflight"] = True
