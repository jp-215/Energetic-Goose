"""Pydantic models for service metadata endpoints."""

from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str


class PlatformInfo(BaseModel):
    id: str
    label: str


class ModelsResponse(BaseModel):
    platform: PlatformInfo
    models: List[str]


class RolesResponse(BaseModel):
    role_models: Dict[str, str]
    role_instructions: Dict[str, str]
    inference_config: Dict[str, float]
