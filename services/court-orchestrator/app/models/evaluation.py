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


class TokenUsage(BaseModel):
    prompt: int = 0
    completion: int = 0
    total: int = 0
    estimated: bool = False


class BenchmarkItemResult(BaseModel):
    id: str
    question: str
    choices: Optional[List[str]] = None
    response: str
    expected: str
    predicted: Optional[str]
    correct: bool
    latency_ms: int
    tokens: TokenUsage = Field(default_factory=TokenUsage)
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
    tokens: TokenUsage = Field(default_factory=TokenUsage)
    items: List[BenchmarkItemResult]


class Turn(BaseModel):
    id: str
    index: int
    round: int = 0
    role: str  # user (persona) | assistant (model under test)
    by: str = "script"  # simulator | target | script — who spent the tokens
    content: str
    latency_ms: int = 0
    tokens: TokenUsage = Field(default_factory=TokenUsage)
    error: Optional[str] = None


class RoundUsage(BaseModel):
    round: int
    simulator_tokens: int
    target_tokens: int
    total_tokens: int
    latency_ms: int


class AgentTokens(BaseModel):
    target: TokenUsage = Field(default_factory=TokenUsage)
    simulator: TokenUsage = Field(default_factory=TokenUsage)
    feedback: TokenUsage = Field(default_factory=TokenUsage)
    total: TokenUsage = Field(default_factory=TokenUsage)


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
    rounds: List[RoundUsage] = Field(default_factory=list)
    tokens: AgentTokens = Field(default_factory=AgentTokens)
    feedback: Optional[Feedback]
    score: float
    status: str
    error: Optional[str] = None


class StageProgress(BaseModel):
    status: str = "pending"  # pending | running | done | error
    done: int = 0
    total: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    seconds: Optional[float] = None


class Progress(BaseModel):
    stage: str
    units_done: int
    units_total: int
    percent: float
    elapsed_s: float
    eta_s: Optional[float] = None
    eta_is_estimate: bool = True
    stages: Dict[str, StageProgress]
    tokens: TokenUsage = Field(default_factory=TokenUsage)
    tokens_by_stage: Dict[str, Any] = Field(default_factory=dict)


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
    progress: Optional[Progress] = None
    tokens: Optional[Dict[str, Any]] = None
    timings: Optional[Dict[str, float]] = None
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
    percent: Optional[float] = None
    eta_s: Optional[float] = None
    total_tokens: Optional[int] = None


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


class ModelProbeRequest(BaseModel):
    models: Optional[List[str]] = Field(None, description="Default: every model on the platform")


class ModelProbeResult(BaseModel):
    model: str
    accessible: bool
    latency_ms: int
    error: Optional[str] = None
    tokens: TokenUsage = Field(default_factory=TokenUsage)


class ModelProbeResponse(BaseModel):
    results: List[ModelProbeResult]
    accessible: List[str]
