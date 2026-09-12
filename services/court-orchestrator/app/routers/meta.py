"""Metadata router: health, supported models, role configuration."""

from __future__ import annotations

from fastapi import APIRouter

from ..handlers import meta as meta_handler
from ..models.meta import HealthResponse, ModelsResponse, RolesResponse

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return await meta_handler.handle_health()


@router.get("/models", response_model=ModelsResponse)
async def models() -> ModelsResponse:
    return await meta_handler.handle_models()


@router.get("/roles", response_model=RolesResponse)
async def roles() -> RolesResponse:
    return await meta_handler.handle_roles()
