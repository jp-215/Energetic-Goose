"""Pydantic data-validation models for court cases."""

from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, Field


class CaseRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    context: str = Field("", max_length=20000, description="Case facts / background")
    query: str = Field("", max_length=5000, description="The question before the court")
    model_overrides: Optional[Dict[str, str]] = Field(
        None, description="Optional role -> model id overrides (simple/complex/judge)"
    )


class RoleResult(BaseModel):
    role: str
    model: str
    answer: str
    verdict: str
    confidence: Optional[float]
    rationale: str
    latency_ms: int
    retries_used: int
    status: str
    error: Optional[str] = None


class CaseResponse(BaseModel):
    case_id: str
    title: str
    final_verdict: str
    judge_rationale: str
    roles: Dict[str, RoleResult]
    total_latency_ms: int
    total_retries: int
    status: str
    error: Optional[str] = None
