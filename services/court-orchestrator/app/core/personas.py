"""Persona-agent registry: built-in personalities plus imported ones.

Personas are stored in the personas JSON collection. On first access the
collection is seeded with the five built-in personalities from
app/data/personas/default_personas.json. Imported personas are validated by
the Pydantic model in models/persona.py before they reach this module.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import FEEDBACK_DIMENSIONS
from .store import personas as collection

DEFAULTS_PATH = Path(__file__).resolve().parent.parent / "data" / "personas" / "default_personas.json"


def load_default_personas() -> List[Dict[str, Any]]:
    payload = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    for persona in payload:
        persona["builtin"] = True
    return payload


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "persona"


def normalize_priorities(priorities: Optional[Dict[str, float]]) -> Dict[str, float]:
    """Fill missing dimensions and normalise weights to sum to 1."""
    raw = {dim: float((priorities or {}).get(dim, 0.0) or 0.0) for dim in FEEDBACK_DIMENSIONS}
    total = sum(raw.values())
    if total <= 0:
        return {dim: 1.0 / len(FEEDBACK_DIMENSIONS) for dim in FEEDBACK_DIMENSIONS}
    return {dim: round(v / total, 4) for dim, v in raw.items()}


def _ensure_seeded() -> None:
    if not collection.all():
        for persona in load_default_personas():
            collection.put(persona["id"], persona)


def list_personas() -> List[Dict[str, Any]]:
    _ensure_seeded()
    return sorted(collection.all(), key=lambda p: (not p.get("builtin", False), p.get("name", "")))


def get_persona(persona_id: str) -> Optional[Dict[str, Any]]:
    _ensure_seeded()
    return collection.get(persona_id)


def upsert_persona(persona: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_seeded()
    persona = dict(persona)
    persona["id"] = persona.get("id") or slugify(persona["name"])
    persona["priorities"] = normalize_priorities(persona.get("priorities"))
    existing = collection.get(persona["id"])
    persona["builtin"] = bool(existing and existing.get("builtin"))
    return collection.put(persona["id"], persona)


def import_personas(payload: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [upsert_persona(p) for p in payload]


def delete_persona(persona_id: str) -> bool:
    _ensure_seeded()
    return collection.delete(persona_id)


def reset_builtin_personas() -> List[Dict[str, Any]]:
    """Restore the built-in five to their shipped definitions (imported ones are kept)."""
    for persona in load_default_personas():
        collection.put(persona["id"], persona)
    return list_personas()


def resolve_personas(agent_ids: Optional[List[str]]) -> List[Dict[str, Any]]:
    """Personas for a run: the requested ids in order, or every persona."""
    available = {p["id"]: p for p in list_personas()}
    if not agent_ids:
        return list(available.values())
    missing = [a for a in agent_ids if a not in available]
    if missing:
        raise KeyError(f"unknown persona id(s): {missing}")
    return [available[a] for a in agent_ids]
