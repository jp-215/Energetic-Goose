"""AI Court service (public, :8000).

The single backend service: it owns the role logic and all Canopy Wave
model calls, and serves the frontend directly. One dedicated terminal
runs the whole chain: middleware (env_loader -> cors -> datacat ->
preflight) -> models -> handlers -> routers -> frontend.
"""

from __future__ import annotations

if __package__ in (None, ""):  # executed as `python main.py` — bootstrap package context
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "app"

from fastapi import FastAPI

from .core.config import (
    CORS_ORIGINS,
    get_api_key,
    get_base_url,
    get_hub_models,
    get_role_models,
    mask_secret,
)
from .middleware import install_all
from .routers import court, hub, meta

SERVICE_NAME = "court-orchestrator"


def _banner_extra() -> dict:
    role_models = get_role_models()
    return {
        "base url": get_base_url(),
        "api key": mask_secret(get_api_key()),
        "cors origins": ", ".join(CORS_ORIGINS),
        **{f"role/{role}": model for role, model in role_models.items()},
        **{f"hub/{role}": model for role, model in get_hub_models().items()},
    }


def create_app() -> FastAPI:
    app = FastAPI(title="AI Court Orchestrator", version="0.3.0")
    install_all(
        app,
        service_name=SERVICE_NAME,
        cors_origins=CORS_ORIGINS,  # the frontend talks to this service directly
        banner_extra=_banner_extra,
    )
    app.include_router(meta.router)
    app.include_router(court.router)
    app.include_router(hub.router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
