"""Metadata business logic: health, supported models, role configuration."""

from __future__ import annotations

from fastapi import HTTPException

from ..core.canopy import fetch_supported_model_ids
from ..core.config import INFERENCE_CONFIG, PLATFORM, ROLE_INSTRUCTIONS, get_role_models
from ..models.meta import HealthResponse, ModelsResponse, RolesResponse

SERVICE_NAME = "court-orchestrator"


async def handle_health() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME)


async def handle_models() -> ModelsResponse:
    try:
        models = await fetch_supported_model_ids()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Canopy Wave unreachable: {exc}") from exc
    return ModelsResponse(platform=PLATFORM, models=models)


async def handle_roles() -> RolesResponse:
    return RolesResponse(
        role_models=get_role_models(),
        role_instructions=ROLE_INSTRUCTIONS,
        inference_config=INFERENCE_CONFIG,
    )
