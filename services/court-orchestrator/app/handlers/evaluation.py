"""Model-evaluation business logic.

A session evaluates ONE model in three stages:

  1. benchmarks  — open-source benchmark subsets (MMLU, GSM8K, ...)
  2. agents      — persona agents use the model and grade the experience
  3. scoring     — final = w_bench * benchmark_score + w_agents * agent_score

Every step is persisted to the sessions store as it happens (so a running
session can be viewed live), a `progress` event with percent / elapsed / ETA /
tokens is emitted after every model call, and the interaction graph (Neo4j or
the in-memory fallback) is updated off the event loop.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import random
import time
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
from ..core.graph import Neo4jGraphStore, get_graph
from ..core.llm import add_usage, chat, empty_usage
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
                 benches: List[Dict[str, Any]]) -> Dict[str, Any]:
    w_bench = EVAL_WEIGHTS["benchmark"] if req.benchmark_weight is None else req.benchmark_weight
    items = req.items_per_benchmark or EVAL_CONFIG["items_per_benchmark"]
    turns = req.agent_turns or EVAL_CONFIG["agent_turns"]
    bench_units = sum(min(items, len(b["items"])) for b in benches)
    # per agent: (turns - 1) simulator messages + turns target replies + 1 feedback form
    agent_units = len(personas) * (2 * turns)
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
            "items_per_benchmark": items,
            "agent_turns": turns,
            "seed": req.seed if req.seed is not None else random.randint(1, 10**6),
            "agent_ids": [p["id"] for p in personas],
            "benchmarks": [b["name"] for b in benches],
            "mock_mode": is_mock_mode(),
        },
        "benchmark_score": None,
        "agent_score": None,
        "final_score": None,
        "benchmarks": [],
        "agents": [],
        "progress": {
            "stage": "queued",
            "units_done": 0,
            "units_total": bench_units + agent_units,
            "percent": 0.0,
            "elapsed_s": 0.0,
            "eta_s": None,
            "eta_is_estimate": True,
            "stages": {
                "benchmarks": {"status": "pending", "done": 0, "total": bench_units},
                "agents": {"status": "pending", "done": 0, "total": agent_units},
                "scoring": {"status": "pending", "done": 0, "total": 1},
            },
            "tokens": empty_usage(),
            "tokens_by_stage": {
                "benchmarks": empty_usage(),
                "agents": {"target": empty_usage(), "simulator": empty_usage()},
            },
        },
        "tokens": None,
        "timings": None,
        "error": None,
    }


def _save(session: Dict[str, Any]) -> None:
    session_store.put(session["id"], session)


def _summary(session: Dict[str, Any]) -> Dict[str, Any]:
    progress = session.get("progress") or {}
    return {
        key: session.get(key)
        for key in (
            "id", "label", "model", "vendor", "region", "created_at", "finished_at",
            "status", "stage", "benchmark_score", "agent_score", "final_score",
        )
    } | {
        "agent_count": len(session.get("agents", [])),
        "benchmark_count": len(session.get("benchmarks", [])),
        "percent": progress.get("percent"),
        "eta_s": progress.get("eta_s"),
        "total_tokens": (progress.get("tokens") or {}).get("total"),
    }


# ---------------------------------------------------------------------------
# Progress / ETA bookkeeping
# ---------------------------------------------------------------------------

class ProgressTracker:
    """Counts completed model calls per stage and predicts the remaining time.

    ETA = remaining benchmark items x measured wall-clock per item
        + remaining agent calls x measured wall-clock per agent call
    Until the agent stage has produced data, its rate is extrapolated from the
    benchmark call latency (agent replies are longer, but agents run in
    parallel), and the ETA is flagged as an estimate.
    """

    def __init__(self, session: Dict[str, Any], n_agents: int):
        self.session = session
        self.p = session["progress"]
        self.started = time.perf_counter()
        self.stage_started: Dict[str, float] = {}
        self.n_agents = max(1, n_agents)
        self.bench_latencies_ms: List[int] = []
        self.agent_started = False

    # -- stages ---------------------------------------------------------------
    def start_stage(self, stage: str) -> None:
        self.stage_started[stage] = time.perf_counter()
        self.p["stage"] = stage
        self.session["stage"] = stage
        self.p["stages"][stage]["status"] = "running"
        self.p["stages"][stage]["started_at"] = _now()
        if stage == "agents":
            self.agent_started = True
        self._recompute()

    def finish_stage(self, stage: str, status: str = "done") -> None:
        st = self.p["stages"][stage]
        st["status"] = status
        st["finished_at"] = _now()
        st["seconds"] = round(time.perf_counter() - self.stage_started.get(stage, self.started), 2)
        if status == "done":
            st["done"] = st["total"]
        self._recompute()

    # -- units ----------------------------------------------------------------
    def bench_item(self, tokens: Dict[str, Any], latency_ms: int) -> None:
        self.p["stages"]["benchmarks"]["done"] += 1
        self.bench_latencies_ms.append(latency_ms)
        add_usage(self.p["tokens_by_stage"]["benchmarks"], tokens)
        add_usage(self.p["tokens"], tokens)
        self._recompute()

    def agent_call(self, by: str, tokens: Dict[str, Any]) -> None:
        self.p["stages"]["agents"]["done"] += 1
        if by in ("target", "simulator"):
            add_usage(self.p["tokens_by_stage"]["agents"][by], tokens)
        add_usage(self.p["tokens"], tokens)
        self._recompute()

    # -- maths ----------------------------------------------------------------
    def _recompute(self) -> None:
        p = self.p
        st = p["stages"]
        now = time.perf_counter()
        p["elapsed_s"] = round(now - self.started, 1)
        done = st["benchmarks"]["done"] + st["agents"]["done"]
        p["units_done"] = done
        p["percent"] = min(100.0, round(100.0 * done / p["units_total"], 1)) if p["units_total"] else 0.0

        # measured wall-clock per benchmark item (concurrency already baked in)
        bench_rate = None
        if st["benchmarks"]["done"]:
            elapsed = now - self.stage_started.get("benchmarks", self.started)
            bench_rate = elapsed / st["benchmarks"]["done"]

        # measured wall-clock per agent call, or extrapolated from benchmark latency
        agent_rate, estimate = None, True
        if st["agents"]["done"] and self.agent_started:
            elapsed = now - self.stage_started.get("agents", now)
            agent_rate = elapsed / st["agents"]["done"]
            estimate = st["agents"]["done"] < self.n_agents  # too few samples yet
        elif self.bench_latencies_ms:
            avg_call_s = sum(self.bench_latencies_ms) / len(self.bench_latencies_ms) / 1000.0
            # agent replies are ~3.5x longer than a one-letter answer; agents run in parallel
            agent_rate = max(0.5, avg_call_s * 3.5 / self.n_agents)

        remaining_bench = st["benchmarks"]["total"] - st["benchmarks"]["done"]
        remaining_agent = st["agents"]["total"] - st["agents"]["done"]
        eta = 0.0
        known = True
        if remaining_bench:
            if bench_rate is None:
                known = False
            else:
                eta += remaining_bench * bench_rate
        if remaining_agent:
            if agent_rate is None:
                known = False
            else:
                eta += remaining_agent * agent_rate
        p["eta_s"] = round(eta, 1) if known else None
        p["eta_is_estimate"] = estimate or not known

    def snapshot(self) -> Dict[str, Any]:
        # deep copy: the event sits in a queue while the tracker keeps mutating
        return {"event": "progress", "session_id": self.session["id"],
                **json.loads(json.dumps(self.p))}


# ---------------------------------------------------------------------------
# Graph mirroring (runs in a worker thread: Neo4j round-trips must not block
# the event loop that is streaming progress to the client)
# ---------------------------------------------------------------------------

async def _graph(fn, *args) -> None:
    try:
        await asyncio.to_thread(fn, *args)
    except Exception as exc:  # the graph is a mirror; never fail the session over it
        import logging

        logging.getLogger("datacat").warning("graph mirror failed in %s: %s", fn.__name__, exc)


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
                {"score": result["score"], "correct": result["correct"], "total": result["total"],
                 "tokens": result["tokens"]["total"]})


def _graph_turn(session: Dict[str, Any], persona: Dict[str, Any], turn: Dict[str, Any],
                previous_turn_id: Optional[str]) -> None:
    g = get_graph()
    turn_id = f"{session['id']}:{persona['id']}:{turn['index']}"
    g.merge_node("Turn", {
        "id": turn_id, "index": turn["index"], "round": turn.get("round", 0),
        "role": turn["role"], "by": turn.get("by", ""),
        "content": turn["content"][:1500], "latency_ms": turn.get("latency_ms", 0),
        "tokens": int((turn.get("tokens") or {}).get("total", 0)),
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
        "tokens": int(agent_result["tokens"]["total"]["total"]),
        **{f"rating_{k}": v for k, v in (fb.get("ratings") or {}).items()},
    })
    g.merge_rel("Agent", agent_result["agent_id"], "GAVE", "Feedback", fid)
    g.merge_rel("Feedback", fid, "ABOUT", "Model", session["model"])
    g.merge_rel("Feedback", fid, "IN_SESSION", "Session", session["id"])
    g.merge_rel("Agent", agent_result["agent_id"], "INTERACTED_WITH", "Model", session["model"], {
        "session_id": session["id"], "turns": len(agent_result["turns"]),
        "score": agent_result["score"], "scenario": agent_result["scenario_title"],
        "tokens_target": int(agent_result["tokens"]["target"]["total"]),
        "tokens_simulator": int(agent_result["tokens"]["simulator"]["total"]),
    })


def _graph_session_end(session: Dict[str, Any]) -> None:
    get_graph().merge_node("Session", {
        "id": session["id"], "status": session["status"], "finished_at": session["finished_at"],
        "benchmark_score": session["benchmark_score"], "agent_score": session["agent_score"],
        "final_score": session["final_score"],
        "total_tokens": int(((session.get("tokens") or {}).get("total") or {}).get("total", 0)),
        "total_seconds": (session.get("timings") or {}).get("total_s"),
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
    session = _new_session(model, req, personas, benches)
    _save(session)
    await _graph(_graph_session_start, session, personas)
    yield {"event": "session_created", "session": _summary(session)}

    queue: asyncio.Queue = asyncio.Queue()
    cfg = session["config"]
    tracker = ProgressTracker(session, len(personas))
    save_lock = asyncio.Lock()

    async def push(event: Dict[str, Any]) -> None:
        await queue.put(event)

    async def progress() -> None:
        await push(tracker.snapshot())

    async def persist() -> None:
        async with save_lock:
            _save(session)

    async def do_benchmarks() -> None:
        tracker.start_stage("benchmarks")
        await persist()
        await push({"event": "stage", "session_id": session["id"], "stage": "benchmarks",
                    "benchmarks": [b["name"] for b in benches]})
        await progress()
        for bench in benches:
            done = {"n": 0}
            total = min(cfg["items_per_benchmark"], len(bench["items"]))

            async def on_item(record, bench=bench, done=done, total=total):
                done["n"] += 1
                tracker.bench_item(record["tokens"], record["latency_ms"])
                await push({"event": "benchmark_item", "session_id": session["id"],
                            "benchmark": bench["name"], "done": done["n"], "total": total,
                            "correct": record["correct"], "item_id": record["id"],
                            "tokens": record["tokens"], "latency_ms": record["latency_ms"]})
                await progress()

            result = await bench_core.run_benchmark(
                model, bench, cfg["items_per_benchmark"], cfg["seed"], on_item
            )
            session["benchmarks"].append(result)
            await persist()
            await _graph(_graph_benchmark, session, result)
            await push({"event": "benchmark_result", "session_id": session["id"],
                        "result": {k: v for k, v in result.items() if k != "items"}})
        scores = [b["score"] for b in session["benchmarks"]]
        session["benchmark_score"] = round(sum(scores) / len(scores), 2) if scores else 0.0
        tracker.finish_stage("benchmarks")
        await persist()

    async def do_agents() -> None:
        tracker.start_stage("agents")
        await persist()
        await push({"event": "stage", "session_id": session["id"], "stage": "agents",
                    "agents": [p["id"] for p in personas]})
        await progress()

        gate = asyncio.Semaphore(EVAL_CONFIG["agent_concurrency"])

        async def one(persona: Dict[str, Any]) -> Dict[str, Any]:
            async with gate:
                return await _one(persona)

        async def _one(persona: Dict[str, Any]) -> Dict[str, Any]:
            last = {"id": None}

            async def on_turn(turn, persona=persona, last=last):
                await _graph(_graph_turn, session, persona, turn, last["id"])
                last["id"] = f"{session['id']}:{persona['id']}:{turn['index']}"
                if turn.get("by") in ("target", "simulator"):
                    tracker.agent_call(turn["by"], turn["tokens"])
                await push({"event": "agent_turn", "session_id": session["id"],
                            "agent_id": persona["id"], "agent_name": persona["name"],
                            "turn": turn})
                await progress()

            result = await run_agent(model, session["simulator_model"], persona,
                                     cfg["agent_turns"], on_turn)
            # the feedback form is the agent's last model call
            tracker.agent_call("simulator", result["tokens"]["feedback"])
            session["agents"].append(result)
            await persist()
            await _graph(_graph_feedback, session, result)
            await push({"event": "agent_feedback", "session_id": session["id"],
                        "agent_id": persona["id"], "agent_name": persona["name"],
                        "score": result["score"], "status": result["status"],
                        "feedback": result["feedback"], "tokens": result["tokens"],
                        "rounds": result["rounds"]})
            await progress()
            return result

        await asyncio.gather(*(one(p) for p in personas))
        graded = [a["score"] for a in session["agents"] if a["status"] != "error"]
        session["agent_score"] = round(sum(graded) / len(graded), 2) if graded else 0.0
        tracker.finish_stage("agents")
        await persist()

    def do_scoring() -> None:
        tracker.start_stage("scoring")
        w = session["weights"]
        session["final_score"] = round(
            w["benchmark"] * (session["benchmark_score"] or 0.0)
            + w["agents"] * (session["agent_score"] or 0.0), 2
        )
        # token + timing roll-ups
        bench_tokens = empty_usage()
        for b in session["benchmarks"]:
            add_usage(bench_tokens, b["tokens"])
        target, simulator = empty_usage(), empty_usage()
        for a in session["agents"]:
            add_usage(target, a["tokens"]["target"])
            add_usage(simulator, a["tokens"]["simulator"])
        total = add_usage(add_usage(add_usage(empty_usage(), bench_tokens), target), simulator)
        session["tokens"] = {
            "benchmarks": bench_tokens,
            "agents": {"target": target, "simulator": simulator,
                       "total": add_usage(add_usage(empty_usage(), target), simulator)},
            "model_under_test": add_usage(add_usage(empty_usage(), bench_tokens), target),
            "total": total,
            "per_benchmark": {b["name"]: b["tokens"] for b in session["benchmarks"]},
            "per_agent": {a["agent_id"]: a["tokens"] for a in session["agents"]},
        }
        st = tracker.p["stages"]
        session["timings"] = {
            "benchmarks_s": st["benchmarks"].get("seconds") or 0.0,
            "agents_s": st["agents"].get("seconds") or 0.0,
            "total_s": round(time.perf_counter() - tracker.started, 2),
        }
        tracker.finish_stage("scoring")
        session["status"] = "done"
        session["stage"] = "done"
        tracker.p["stage"] = "done"
        tracker.p["eta_s"] = 0.0
        tracker.p["percent"] = 100.0

    async def pipeline() -> None:
        try:
            await do_benchmarks()
            await do_agents()
            do_scoring()
        except Exception as exc:  # keep the session document consistent on failure
            session["status"] = "error"
            session["stage"] = "error"
            session["error"] = str(exc)
            tracker.p["stage"] = "error"
            for stage in tracker.p["stages"].values():
                if stage["status"] == "running":
                    stage["status"] = "error"
        finally:
            session["finished_at"] = _now()
            await persist()
            await _graph(_graph_session_end, session)
            await queue.put(None)

    task = asyncio.create_task(pipeline())
    while True:
        event = await queue.get()
        if event is None:
            break
        yield event
    await task
    yield tracker.snapshot()
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
# Sessions / rankings / graph / meta / probe
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


PAPERS_CYPHER = (
    "MATCH (n) WHERE n:Paper OR n:KnowledgeNode\n"
    "OPTIONAL MATCH (n)-[r]-(m) WHERE m:Paper OR m:KnowledgeNode\n"
    "RETURN n, r, m"
)


def papers_graph() -> Dict[str, Any]:
    """The papers / knowledge corpus living in the shared Neo4j instance
    (same Aura DB as the interaction graph; separate labels)."""
    g = get_graph()
    if not isinstance(g, Neo4jGraphStore):
        raise HTTPException(
            status_code=409,
            detail="papers graph requires the Neo4j backend (set NEO4J_URI)",
        )
    try:
        sub = g.papers_subgraph()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"graph backend error: {exc}") from exc
    return {"backend": g.backend, "session_id": "", "cypher": PAPERS_CYPHER, **sub}


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


async def probe_models(models: Optional[List[str]]) -> Dict[str, Any]:
    """One tiny call per model to find out which ids this key can actually use."""
    if not models:
        try:
            models = await fetch_supported_model_ids()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"platform unreachable: {exc}") from exc

    async def one(model: str) -> Dict[str, Any]:
        result = await chat(model, [{"role": "user", "content": "Reply with the single letter B."}],
                            temperature=0.0, max_tokens=64, purpose="benchmark_mc")
        return {"model": model, "accessible": result.status == "ok",
                "latency_ms": result.latency_ms, "error": result.error,
                "tokens": result.usage or empty_usage()}

    results = await asyncio.gather(*(one(m) for m in models))
    return {"results": list(results), "accessible": [r["model"] for r in results if r["accessible"]]}


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
