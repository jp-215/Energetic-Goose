"""Pydantic data-validation models for the The Firm (multi-agent dev team)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..core.config import HUB_LIMITS


class HubRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    context: str = Field("", max_length=30000, description="Project brief / background")
    goal: str = Field("", max_length=5000, description="What the team must deliver")
    model_overrides: Optional[Dict[str, str]] = Field(
        None, description="Optional role -> model id overrides (planner/engineer/integrator)"
    )
    max_agents: Optional[int] = Field(
        None, ge=1, le=HUB_LIMITS["max_team_size"],
        description="Upper bound on team size the planner may choose",
    )


class TaskSpec(BaseModel):
    id: str
    title: str
    description: str = ""
    deliverables: List[str] = Field(default_factory=list)


class AgentSpec(BaseModel):
    id: str
    name: str
    role: str
    specialty: str = ""
    tasks: List[TaskSpec] = Field(default_factory=list)
    parent_id: Optional[str] = None
    depth: int = 0
    summoned_reason: Optional[str] = None


class TeamPlan(BaseModel):
    analysis: str
    team_size: int
    rationale: str
    agents: List[AgentSpec]
    integration_notes: str = ""
    fallback: bool = False


class CallTrace(BaseModel):
    """Everything needed to audit one model call from the UI."""

    role: str
    model: str
    system_prompt: str
    user_prompt: str
    raw_output: str
    latency_ms: int
    retries_used: int
    status: str
    error: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    finish_reason: Optional[str] = None


class WorkspaceFile(BaseModel):
    path: str = Field(..., min_length=1, max_length=400)
    content: str = Field("", max_length=400000)
    author: str = ""


class HelpRequest(BaseModel):
    role: str
    task: str
    reason: str = ""


class AgentResult(BaseModel):
    agent_id: str
    status: str
    summary: str = ""
    notes: str = ""
    files: List[WorkspaceFile] = Field(default_factory=list)
    help_request: Optional[HelpRequest] = None
    helper_id: Optional[str] = None
    call: CallTrace


class IntegrationResult(BaseModel):
    status: str
    summary: str = ""
    run_instructions: str = ""
    files: List[WorkspaceFile] = Field(default_factory=list)
    call: CallTrace


class HubResponse(BaseModel):
    run_id: str
    title: str
    status: str
    plan: Optional[TeamPlan] = None
    agents: List[AgentResult] = Field(default_factory=list)
    integration: Optional[IntegrationResult] = None
    workspace: List[WorkspaceFile] = Field(default_factory=list)
    trace: List[Dict[str, Any]] = Field(default_factory=list)
    total_latency_ms: int
    total_calls: int
    total_retries: int
    error: Optional[str] = None


class PlanResponse(BaseModel):
    run_id: str
    plan: TeamPlan
    call: CallTrace


class HubRolesResponse(BaseModel):
    hub_models: Dict[str, str]
    hub_instructions: Dict[str, str]
    limits: Dict[str, int]


class ExportRequest(BaseModel):
    run_id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{4,40}$")
    files: List[WorkspaceFile] = Field(..., min_length=1)
    manifest: Optional[Dict[str, Any]] = Field(
        None, description="Run metadata written to .hub/run.json for traceability"
    )


class ExportResponse(BaseModel):
    run_id: str
    path: str
    file_count: int


class PublishRequest(BaseModel):
    run_id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{4,40}$")
    repo_name: str = Field(..., pattern=r"^[A-Za-z0-9._-]{1,100}$")
    private: bool = True
    description: str = Field("", max_length=350)


class PublishResponse(BaseModel):
    run_id: str
    repo_url: str
    path: str
