"""Evaluation router: run sessions, manage them, rank models, inspect the graph."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..handlers import evaluation as eval_handler
from ..models.evaluation import (
    CypherRequest,
    EvalMetaResponse,
    EvaluationRequest,
    GraphResponse,
    RankingsResponse,
    Session,
    SessionListResponse,
)

router = APIRouter(prefix="/api/eval", tags=["evaluation"])


def _ndjson(agen):
    async def lines():
        try:
            async for event in agen:
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except Exception as exc:  # surface mid-stream failures as a final event
            yield json.dumps({"event": "error", "detail": str(exc)}) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson")


@router.get("/meta", response_model=EvalMetaResponse)
async def meta() -> Dict[str, Any]:
    return await eval_handler.eval_meta()


@router.post("/run", response_model=List[Session])
async def run(req: EvaluationRequest) -> List[Dict[str, Any]]:
    """Blocking run: returns the finished session(s)."""
    eval_handler._resolve_inputs(req)  # validate before any work starts
    return await eval_handler.run_many(req)


@router.post("/run/stream")
async def run_stream(req: EvaluationRequest) -> StreamingResponse:
    """Event-driven run: NDJSON, one event per benchmark item / agent turn / result."""
    eval_handler._resolve_inputs(req)
    return _ndjson(eval_handler.run_many_events(req))


@router.get("/sessions", response_model=SessionListResponse)
async def sessions() -> Dict[str, Any]:
    return {"sessions": eval_handler.list_sessions()}


@router.get("/sessions/{session_id}", response_model=Session)
async def session(session_id: str) -> Dict[str, Any]:
    return eval_handler.get_session(session_id)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> Dict[str, Any]:
    return eval_handler.delete_session(session_id)


@router.post("/sessions/{session_id}/rerun/stream")
async def rerun_session(session_id: str) -> StreamingResponse:
    req = eval_handler.rerun_request(session_id)
    return _ndjson(eval_handler.run_many_events(req))


@router.get("/sessions/{session_id}/graph", response_model=GraphResponse)
async def session_graph(session_id: str) -> Dict[str, Any]:
    return eval_handler.session_graph(session_id)


@router.get("/rankings", response_model=RankingsResponse)
async def rankings() -> Dict[str, Any]:
    return eval_handler.rankings()


@router.get("/graph/status")
async def graph_status() -> Dict[str, Any]:
    return eval_handler.graph_status()


@router.post("/graph/cypher")
async def graph_cypher(req: CypherRequest) -> Dict[str, Any]:
    """Read-only Cypher against the Neo4j backend (409 when running in-memory)."""
    return eval_handler.run_cypher(req.query, req.params)
