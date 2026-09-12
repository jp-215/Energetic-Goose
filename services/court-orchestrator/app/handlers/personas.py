"""Persona-agent business logic: list, import, update, delete, reset."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import HTTPException

from ..core import personas as persona_core
from ..core.config import FEEDBACK_DIMENSIONS
from ..models.persona import Persona


def list_personas() -> Dict[str, Any]:
    return {"personas": persona_core.list_personas(), "dimensions": FEEDBACK_DIMENSIONS}


def get_persona(persona_id: str) -> Dict[str, Any]:
    persona = persona_core.get_persona(persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail=f"persona {persona_id} not found")
    return persona


def import_personas(personas: List[Persona]) -> Dict[str, Any]:
    imported = persona_core.import_personas([p.model_dump() for p in personas])
    return {"imported": [p["id"] for p in imported], "personas": persona_core.list_personas()}


def update_persona(persona_id: str, persona: Persona) -> Dict[str, Any]:
    if not persona_core.get_persona(persona_id):
        raise HTTPException(status_code=404, detail=f"persona {persona_id} not found")
    doc = persona.model_dump()
    doc["id"] = persona_id
    return persona_core.upsert_persona(doc)


def delete_persona(persona_id: str) -> Dict[str, Any]:
    if not persona_core.delete_persona(persona_id):
        raise HTTPException(status_code=404, detail=f"persona {persona_id} not found")
    return {"deleted": persona_id}


def reset_personas() -> Dict[str, Any]:
    return {"personas": persona_core.reset_builtin_personas(), "dimensions": FEEDBACK_DIMENSIONS}
