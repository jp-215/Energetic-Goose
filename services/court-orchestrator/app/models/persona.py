"""Pydantic models for persona agents (import / CRUD payloads)."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class Scenario(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    goal: str = Field("", max_length=2000)
    opening_message: str = Field(..., min_length=1, max_length=6000)
    success_criteria: List[str] = Field(default_factory=list)


class Persona(BaseModel):
    id: Optional[str] = Field(None, max_length=80, description="slug; derived from name if omitted")
    name: str = Field(..., min_length=1, max_length=120)
    avatar: str = Field("🙂", max_length=8)
    tagline: str = Field("", max_length=200)
    age: Optional[int] = Field(None, ge=1, le=120)
    occupation: str = Field("", max_length=200)
    language: str = Field("en", max_length=12)
    background: str = Field("", max_length=4000)
    personality_traits: List[str] = Field(default_factory=list)
    communication_style: str = Field("", max_length=2000)
    expertise_level: str = Field("intermediate", pattern="^(novice|intermediate|expert)$")
    patience: int = Field(5, ge=1, le=10, description="1 = gives up instantly, 10 = infinitely patient")
    strictness: int = Field(5, ge=1, le=10, description="How harshly the persona grades")
    priorities: Dict[str, float] = Field(
        default_factory=dict,
        description="Weights over helpfulness/accuracy/clarity/tone/trust (normalised server-side)",
    )
    scenario: Scenario
    builtin: bool = False


class PersonaImport(BaseModel):
    personas: List[Persona] = Field(..., min_length=1, max_length=100)


class PersonaListResponse(BaseModel):
    personas: List[Persona]
    dimensions: List[str]
