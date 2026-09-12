"""Pydantic models for the model-evaluation endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EvaluationRequest(BaseModel):
    models: List[str] = Field(..., min_length=1, max_length=10, description="Model ids to evaluate")
    agent_ids: Optional[List[str]] = Field(None, description="Persona ids; default = all personas")
    benchmarks: Optional[List[str]] = Field(None, description="Benchmark names; default = all")
    items_per_benchmark: Optional[int] = Field(None, ge=1, le=50)
    agent_turns: Optional[int] = Field(None, ge=1, le=6, description="User turns per persona")
    benchmark_weight: Optional[float] = Field(None, ge=0, le=1)
    simulator_model: Optional[str] = Field(None, description="Model that plays the personas")
    seed: Optional[int] = Field(None, description="Sampling seed (defaults to random)")
    label: str = Field("", max_length=120)


class BenchmarkItemResult(BaseModel):
    id: str
    question: str
    choices: Optional[List[str]] = None
    response: str
    expected: str
    predicted: Optional[str]
    correct: bool
    latency_ms: int
    error: Optional[str] = None


class BenchmarkResult(BaseModel):
    name: str
    display_name: str
    source: str
    task_type: str
    total: int
    correct: int
    score: float
    errors: int
    avg_latency_ms: int
    items: List[BenchmarkItemResult]


class Turn(BaseModel):
    id: str
    index: int
    role: str  # user (persona) | assistant (model under test)
    content: str
    latency_ms: int = 0
    error: Optional[str] = None


class Feedback(BaseModel):
    ratings: Dict[str, int]
    would_use_again: bool
    summary: str
    highlights: List[str] = Field(default_factory=list)
    complaints: List[str] = Field(default_factory=list)
    quote: str = ""
    raw: str = ""


class AgentResult(BaseModel):
    agent_id: str
    agent_name: str
    avatar: str
    scenario_title: str
    priorities: Dict[str, float]
    turns: List[Turn]
    feedback: Optional[Feedback]
    score: float
    status: str
    error: Optional[str] = None


class Session(BaseModel):
    id: str
    label: str
    model: str
    vendor: str
    region: str
    simulator_model: str
    created_at: str
    finished_at: Optional[str] = None
    status: str  # running | done | error
    stage: str  # queued | benchmarks | agents | scoring | done | error
    weights: Dict[str, float]
    config: Dict[str, Any]
    benchmark_score: Optional[float] = None
    agent_score: Optional[float] = None
    final_score: Optional[float] = None
    benchmarks: List[BenchmarkResult] = Field(default_factory=list)
    agents: List[AgentResult] = Field(default_factory=list)
    error: Optional[str] = None


class SessionSummary(BaseModel):
    id: str
    label: str
    model: str
    vendor: str
    region: str
    created_at: str
    finished_at: Optional[str]
    status: str
    stage: str
    benchmark_score: Optional[float]
    agent_score: Optional[float]
    final_score: Optional[float]
    agent_count: int
    benchmark_count: int


class SessionListResponse(BaseModel):
    sessions: List[SessionSummary]


class RankingEntry(BaseModel):
    rank: int
    model: str
    vendor: str
    region: str
    sessions: int
    best_final: float
    latest_final: float
    avg_final: float
    avg_benchmark: float
    avg_agents: float
    best_session_id: str
    latest_session_id: str
    last_evaluated: str


class RankingsResponse(BaseModel):
    rankings: List[RankingEntry]
    weights: Dict[str, float]


class GraphNode(BaseModel):
    id: str
    label: str
    properties: Dict[str, Any]


class GraphRelationship(BaseModel):
    id: str
    type: str
    from_: str = Field(..., alias="from")
    to: str
    properties: Dict[str, Any]

    model_config = {"populate_by_name": True}


class GraphResponse(BaseModel):
    backend: str
    session_id: str
    cypher: str
    nodes: List[GraphNode]
    relationships: List[GraphRelationship]


class CypherRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    params: Dict[str, Any] = Field(default_factory=dict)


class CatalogEntry(BaseModel):
    id: str
    vendor: str
    region: str


class EvalMetaResponse(BaseModel):
    catalog: List[CatalogEntry]
    platform_models: List[str]
    benchmarks: List[Dict[str, Any]]
    weights: Dict[str, float]
    defaults: Dict[str, Any]
    simulator_model: str
    mock_mode: bool
    graph: Dict[str, Any]
