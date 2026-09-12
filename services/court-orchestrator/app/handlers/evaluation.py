"""Model-evaluation business logic.

A session evaluates ONE model in two halves:

  1. Benchmark session  — open-source benchmark subsets (MMLU, GSM8K, ...)
  2. Agent session      — persona agents use the model and grade the experience

final = w_bench * benchmark_score + w_agents * agent_score   (default 50/50)

Every step is persisted to the sessions store as it happens (so a running
session can be viewed live) and mirrored into the interaction graph (Neo4j or
the in-memory fallback).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import random
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import HTTPException

from ..core import benchmarks as bench_core
from ..core import personas as persona_core
from ..core.agents import run_agent
from ..core.canopy import fetch_supported_model_ids
from ..core.config import (
    EVAL_CONFIG,
    EVAL_WEIGHTS,
    MODEL_CATALOG,
    get_simulator_model,
    is_mock_mode,
    model_region,
)
from ..core.graph import get_graph
from ..core.store import sessions as session_store
from ..models.evaluation import EvaluationRequest


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def _vendor(model: str) -> str:
    for entry in MODEL_CATALOG:
        if entry["id"] == model:
            return entry["vendor"]
    return model.split("/", 1)[0] if "/" in model else "unknown"


# ---------------------------------------------------------------------------
# Session document helpers
# ---------------------------------------------------------------------------

def _new_session(model: str, req: EvaluationRequest, personas: List[Dict[str, Any]],
                 bench_names: List[str]) -> Dict[str, Any]:
    w_bench = EVAL_WEIGHTS["benchmark"] if req.benchmark_weight is None else req.benchmark_weight
    return {
        "id": uuid.uuid4().hex[:12],
        "label": req.label or "",
        "model": model,
        "vendor": _vendor(model),
        "region": model_region(model),
        "simulator_model": req.simulator_model or get_simulator_model(),
        "created_at": _now(),
        "finished_at": None,
        "status": "running",
        "stage": "queued",
        "weights": {"benchmark": round(w_bench, 4), "agents": round(1 - w_bench, 4)},
        "config": {
            "items_per_benchmark": req.items_per_benchmark or EVAL_CONFIG["items_per_benchmark"],
            "agent_turns": req.agent_turns or EVAL_CONFIG["agent_turns"],
            "seed": req.seed if req.seed is not None else random.randint(1, 10**6),
            "agent_ids": [p["id"] for p in personas],
            "benchmarks": bench_names,
            "mock_mode": is_mock_mode(),
        },
        "benchmark_score": None,
        "agent_score": None,
        "final_score": None,
        "benchmarks": [],
        "agents": [],
        "error": None,
    }


def _save(session: Dict[str, Any]) -> None:
    session_store.put(session["id"], session)


def _summary(session: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: session.get(key)
        for key in (
            "id", "label", "model", "vendor", "region", "created_at", "finished_at",
            "status", "stage", "benchmark_score", "agent_score", "final_score",
        )
    } | {
        "agent_count": len(session.get("agents", [])),
        "benchmark_count": len(session.get("benchmarks", [])),
    }


# ---------------------------------------------------------------------------
# Graph mirroring
# ---------------------------------------------------------------------------

def _graph_session_start(session: Dict[str, Any], personas: List[Dict[str, Any]]) -> None:
    g = get_graph()
    g.merge_node("Model", {"name": session["model"], "vendor": session["vendor"],
                           "region": session["region"]})
    g.merge_node("Session", {
        "id": session["id"], "label": session["label"], "model": session["model"],
        "created_at": session["created_at"], "status": session["status"],
        "weight_benchmark": session["weights"]["benchmark"],
        "weight_agents": session["weights"]["agents"],
    })
    g.merge_rel("Session", session["id"], "EVALUATES", "Model", session["model"])
    for persona in personas:
        g.merge_node("Agent", {
            "id": persona["id"], "name": persona["name"], "avatar": persona.get("avatar", ""),
            "role": persona.get("occupation", ""), "traits": persona.get("personality_traits", []),
            "language": persona.get("language", "en"), "builtin": bool(persona.get("builtin")),
        })
        g.merge_rel("Agent", persona["id"], "PARTICIPATED_IN", "Session", session["id"],
                    {"session_id": session["id"]})


def _graph_benchmark(session: Dict[str, Any], result: Dict[str, Any]) -> None:
    g = get_graph()
    g.merge_node("Benchmark", {"name": result["name"], "display_name": result["display_name"],
                               "source": result["source"], "task_type": result["task_type"]})
    g.merge_rel("Session", session["id"], "RAN_BENCHMARK", "Benchmark", result["name"],
                {"score": result["score"], "correct": result["correct"], "total": result["total"]})


def _graph_turn(session: Dict[str, Any], persona: Dict[str, Any], turn: Dict[str, Any],
                previous_turn_id: Optional[str]) -> None:
    g = get_graph()
    turn_id = f"{session['id']}:{persona['id']}:{turn['index']}"
    g.merge_node("Turn", {
        "id": turn_id, "index": turn["index"], "role": turn["role"],
        "content": turn["content"][:1500], "latency_ms": turn.get("latency_ms", 0),
        "session_id": session["id"], "agent_id": persona["id"],
    })
    g.merge_rel("Turn", turn_id, "IN_SESSION", "Session", session["id"])
    if turn["role"] == "user":
        g.merge_rel("Agent", persona["id"], "SENT", "Turn", turn_id)
    else:
        g.merge_rel("Model", session["model"], "REPLIED", "Turn", turn_id)
    if previous_turn_id:
        g.merge_rel("Turn", previous_turn_id, "NEXT", "Turn", turn_id)


def _graph_feedback(session: Dict[str, Any], agent_result: Dict[str, Any]) -> None:
    g = get_graph()
    fb = agent_result.get("feedback") or {}
    fid = f"{session['id']}:{agent_result['agent_id']}:feedback"
    g.merge_node("Feedback", {
        "id": fid, "session_id": session["id"], "agent_id": agent_result["agent_id"],
        "score": agent_result["score"], "status": agent_result["status"],
        "would_use_again": bool(fb.get("would_use_again", False)),
        "summary": fb.get("summary", ""), "quote": fb.get("quote", ""),
        "ratings_json": fb.get("ratings", {}),
        **{f"rating_{k}": v for k, v in (fb.get("ratings") or {}).items()},
    })
    g.merge_rel("Agent", agent_result["agent_id"], "GAVE", "Feedback", fid)
    g.merge_rel("Feedback", fid, "ABOUT", "Model", session["model"])
    g.merge_rel("Feedback", fid, "IN_SESSION", "Session", session["id"])
    g.merge_rel("Agent", agent_result["agent_id"], "INTERACTED_WITH", "Model", session["model"], {
        "session_id": session["id"], "turns": len(agent_result["turns"]),
        "score": agent_result["score"], "scenario": agent_result["scenario_title"],
    })


def _graph_session_end(session: Dict[str, Any]) -> None:
    get_graph().merge_node("Session", {
        "id": session["id"], "status": session["status"], "finished_at": session["finished_at"],
        "benchmark_score": session["benchmark_score"], "agent_score": session["agent_score"],
        "final_score": session["final_score"],
    })


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _resolve_inputs(req: EvaluationRequest):
    try:
        personas = persona_core.resolve_personas(req.agent_ids)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    available = bench_core.load_benchmarks()
    names = req.benchmarks or list(available.keys())
    unknown = [n for n in names if n not in available]
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown benchmark(s): {unknown}")
    if not names:
        raise HTTPException(status_code=422, detail="no benchmarks available")
    return personas, [available[n] for n in names]


async def run_session_events(model: str, req: EvaluationRequest) -> AsyncIterator[Dict[str, Any]]:
    """Evaluate one model, yielding progress events as they happen."""
    personas, benches = _resolve_inputs(req)
    session = _new_session(model, req, personas, [b["name"] for b in benches])
    _save(session)
    _graph_session_start(session, personas)
    yield {"event": "session_created", "session": _summary(session)}

    queue: asyncio.Queue = asyncio.Queue()
    cfg = session["config"]

    async def push(event: Dict[str, Any]) -> None:
        await queue.put(event)

    async def do_benchmarks() -> None:
        session["stage"] = "benchmarks"
        _save(session)
        await push({"event": "stage", "session_id": session["id"], "stage": "benchmarks",
                    "benchmarks": [b["name"] for b in benches]})
        for bench in benches:
            done = {"n": 0}

            async def on_item(record, bench=bench, done=done):
                done["n"] += 1
                await push({"event": "benchmark_item", "session_id": session["id"],
                            "benchmark": bench["name"], "done": done["n"],
                            "total": min(cfg["items_per_benchmark"], len(bench["items"])),
                            "correct": record["correct"], "item_id": record["id"]})

            result = await bench_core.run_benchmark(
                model, bench, cfg["items_per_benchmark"], cfg["seed"], on_item
            )
            session["benchmarks"].append(result)
            _save(session)
            _graph_benchmark(session, result)
            await push({"event": "benchmark_result", "session_id": session["id"],
                        "result": {k: v for k, v in result.items() if k != "items"}})
        scores = [b["score"] for b in session["benchmarks"]]
        session["benchmark_score"] = round(sum(scores) / len(scores), 2) if scores else 0.0
        _save(session)

    async def do_agents() -> None:
        session["stage"] = "agents"
        _save(session)
        await push({"event": "stage", "session_id": session["id"], "stage": "agents",
                    "agents": [p["id"] for p in personas]})

        async def one(persona: Dict[str, Any]) -> Dict[str, Any]:
            last = {"id": None}

            async def on_turn(turn, persona=persona, last=last):
                _graph_turn(session, persona, turn, last["id"])
                last["id"] = f"{session['id']}:{persona['id']}:{turn['index']}"
                await push({"event": "agent_turn", "session_id": session["id"],
                            "agent_id": persona["id"], "agent_name": persona["name"],
                            "turn": turn})

            result = await run_agent(model, session["simulator_model"], persona,
                                     cfg["agent_turns"], on_turn)
            session["agents"].append(result)
            _save(session)
            _graph_feedback(session, result)
            await push({"event": "agent_feedback", "session_id": session["id"],
                        "agent_id": persona["id"], "agent_name": persona["name"],
                        "score": result["score"], "status": result["status"],
                        "feedback": result["feedback"]})
            return result

        await asyncio.gather(*(one(p) for p in personas))
        graded = [a["score"] for a in session["agents"] if a["status"] != "error"]
        session["agent_score"] = round(sum(graded) / len(graded), 2) if graded else 0.0
        _save(session)

    async def pipeline() -> None:
        try:
            await do_benchmarks()
            await do_agents()
            session["stage"] = "scoring"
            w = session["weights"]
            session["final_score"] = round(
                w["benchmark"] * (session["benchmark_score"] or 0.0)
                + w["agents"] * (session["agent_score"] or 0.0), 2
            )
            session["status"] = "done"
            session["stage"] = "done"
        except Exception as exc:  # keep the session document consistent on failure
            session["status"] = "error"
            session["stage"] = "error"
            session["error"] = str(exc)
        finally:
            session["finished_at"] = _now()
            _save(session)
            try:
                _graph_session_end(session)
            except Exception:
                pass
            await queue.put(None)

    task = asyncio.create_task(pipeline())
    while True:
        event = await queue.get()
        if event is None:
            break
        yield event
    await task
    yield {"event": "session_done", "session": session}


async def run_many_events(req: EvaluationRequest) -> AsyncIterator[Dict[str, Any]]:
    """One session per requested model, sequentially (rate-limit friendly)."""
    seen = []
    for model in req.models:
        model = model.strip()
        if not model or model in seen:
            continue
        seen.append(model)
        async for event in run_session_events(model, req):
            yield event
    yield {"event": "all_done", "models": seen}


async def run_many(req: EvaluationRequest) -> List[Dict[str, Any]]:
    finished = []
    async for event in run_many_events(req):
        if event["event"] == "session_done":
            finished.append(event["session"])
    return finished


# ---------------------------------------------------------------------------
# Sessions / rankings / graph / meta
# ---------------------------------------------------------------------------

def list_sessions() -> List[Dict[str, Any]]:
    docs = sorted(session_store.all(), key=lambda s: s["created_at"], reverse=True)
    return [_summary(s) for s in docs]


def get_session(session_id: str) -> Dict[str, Any]:
    doc = session_store.get(session_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    return doc


def delete_session(session_id: str) -> Dict[str, Any]:
    if not session_store.delete(session_id):
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    try:
        get_graph().delete_session(session_id)
    except Exception as exc:
        return {"deleted": session_id, "graph_warning": str(exc)}
    return {"deleted": session_id}


def rerun_request(session_id: str) -> EvaluationRequest:
    doc = get_session(session_id)
    cfg = doc["config"]
    return EvaluationRequest(
        models=[doc["model"]],
        agent_ids=cfg.get("agent_ids"),
        benchmarks=cfg.get("benchmarks"),
        items_per_benchmark=cfg.get("items_per_benchmark"),
        agent_turns=cfg.get("agent_turns"),
        benchmark_weight=doc["weights"]["benchmark"],
        simulator_model=doc.get("simulator_model"),
        label=f"rerun of {session_id}",
    )


def rankings() -> Dict[str, Any]:
    by_model: Dict[str, List[Dict[str, Any]]] = {}
    for doc in session_store.all():
        if doc.get("status") == "done" and doc.get("final_score") is not None:
            by_model.setdefault(doc["model"], []).append(doc)
    rows = []
    for model, docs in by_model.items():
        docs.sort(key=lambda d: d["created_at"])
        best = max(docs, key=lambda d: d["final_score"])
        latest = docs[-1]
        n = len(docs)
        rows.append({
            "model": model,
            "vendor": latest["vendor"],
            "region": latest["region"],
            "sessions": n,
            "best_final": best["final_score"],
            "latest_final": latest["final_score"],
            "avg_final": round(sum(d["final_score"] for d in docs) / n, 2),
            "avg_benchmark": round(sum(d["benchmark_score"] or 0 for d in docs) / n, 2),
            "avg_agents": round(sum(d["agent_score"] or 0 for d in docs) / n, 2),
            "best_session_id": best["id"],
            "latest_session_id": latest["id"],
            "last_evaluated": latest["created_at"],
        })
    rows.sort(key=lambda r: (r["avg_final"], r["best_final"]), reverse=True)
    for i, row in enumerate(rows, start=1):
        row["rank"] = i
    return {"rankings": rows, "weights": EVAL_WEIGHTS}


SESSION_CYPHER = (
    "MATCH (s:Session {id: $session_id})\n"
    "OPTIONAL MATCH (s)-[r1]-(n1)\n"
    "OPTIONAL MATCH (n1)-[r2]-(n2)\n"
    "WHERE (n1:Turn OR n1:Feedback OR n1:Agent)\n"
    "  AND (n2:Agent OR n2:Model OR n2:Turn OR n2:Feedback)\n"
    "  AND coalesce(r2.session_id, $session_id) = $session_id\n"
    "RETURN s, n1, r1, n2, r2"
)


def session_graph(session_id: str) -> Dict[str, Any]:
    get_session(session_id)  # 404 if unknown
    g = get_graph()
    try:
        sub = g.session_subgraph(session_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"graph backend error: {exc}") from exc
    return {
        "backend": g.backend,
        "session_id": session_id,
        "cypher": SESSION_CYPHER.replace("$session_id", f'"{session_id}"'),
        **sub,
    }


def graph_status() -> Dict[str, Any]:
    try:
        return get_graph().status()
    except Exception as exc:
        return {"backend": "unavailable", "connected": False, "error": str(exc)}


def run_cypher(query: str, params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return get_graph().run_cypher(query, params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"cypher failed: {exc}") from exc


async def eval_meta() -> Dict[str, Any]:
    platform_models: List[str] = []
    if not is_mock_mode():
        try:
            platform_models = await fetch_supported_model_ids()
        except Exception:
            platform_models = []
    return {
        "catalog": MODEL_CATALOG,
        "platform_models": platform_models,
        "benchmarks": bench_core.benchmark_summaries(),
        "weights": EVAL_WEIGHTS,
        "defaults": {
            "items_per_benchmark": EVAL_CONFIG["items_per_benchmark"],
            "max_items_per_benchmark": EVAL_CONFIG["max_items_per_benchmark"],
            "agent_turns": EVAL_CONFIG["agent_turns"],
            "max_agent_turns": EVAL_CONFIG["max_agent_turns"],
        },
        "simulator_model": get_simulator_model(),
        "mock_mode": is_mock_mode(),
        "graph": graph_status(),
    }
