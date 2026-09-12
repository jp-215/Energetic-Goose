"""The Firm router: planner / team run / export / publish endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..handlers import hub as hub_handler
from ..models.hub import (
    ExportRequest,
    ExportResponse,
    HubRequest,
    HubResponse,
    HubRolesResponse,
    PlanResponse,
    PublishRequest,
    PublishResponse,
)

router = APIRouter(prefix="/api", tags=["hub"])


@router.get("/hub/roles", response_model=HubRolesResponse)
async def hub_roles() -> HubRolesResponse:
    return await hub_handler.handle_roles()


@router.post("/hub/plan", response_model=PlanResponse)
async def hub_plan(brief: HubRequest) -> PlanResponse:
    """Planner only: analyze the brief and propose the team without building."""
    return await hub_handler.handle_plan(brief)


@router.post("/hub/run", response_model=HubResponse)
async def hub_run(brief: HubRequest) -> HubResponse:
    return await hub_handler.handle_run(brief)


@router.post("/hub/run/stream")
async def hub_run_stream(brief: HubRequest) -> StreamingResponse:
    """Event-driven run: NDJSON stream, one lifecycle event per line."""
    hub_handler.validate_overrides(brief)

    async def event_lines():
        try:
            async for event in hub_handler.run_hub_events(brief):
                yield json.dumps(event) + "\n"
        except Exception as exc:  # surface mid-stream failures as a final event
            yield json.dumps({"event": "error", "detail": str(exc)}) + "\n"

    return StreamingResponse(event_lines(), media_type="application/x-ndjson")


@router.post("/hub/export", response_model=ExportResponse)
async def hub_export(request: ExportRequest) -> ExportResponse:
    return await hub_handler.handle_export(request)


@router.post("/hub/publish", response_model=PublishResponse)
async def hub_publish(request: PublishRequest) -> PublishResponse:
    return await hub_handler.handle_publish(request)
