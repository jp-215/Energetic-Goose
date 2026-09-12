"""Persona router: manage the personalities of the simulated agents."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Body

from ..handlers import personas as persona_handler
from ..models.persona import Persona, PersonaImport, PersonaListResponse

router = APIRouter(prefix="/api/eval/personas", tags=["personas"])


@router.get("", response_model=PersonaListResponse)
async def list_personas() -> Dict[str, Any]:
    return persona_handler.list_personas()


@router.post("/import")
async def import_personas(
    payload: PersonaImport | List[Persona] | Persona = Body(...),
) -> Dict[str, Any]:
    """Import personalities. Accepts {"personas": [...]}, a bare list, or one persona."""
    if isinstance(payload, PersonaImport):
        personas = payload.personas
    elif isinstance(payload, list):
        personas = payload
    else:
        personas = [payload]
    return persona_handler.import_personas(personas)


@router.post("/reset", response_model=PersonaListResponse)
async def reset_personas() -> Dict[str, Any]:
    return persona_handler.reset_personas()


@router.get("/{persona_id}", response_model=Persona)
async def get_persona(persona_id: str) -> Dict[str, Any]:
    return persona_handler.get_persona(persona_id)


@router.put("/{persona_id}", response_model=Persona)
async def update_persona(persona_id: str, persona: Persona) -> Dict[str, Any]:
    return persona_handler.update_persona(persona_id, persona)


@router.delete("/{persona_id}")
async def delete_persona(persona_id: str) -> Dict[str, Any]:
    return persona_handler.delete_persona(persona_id)
