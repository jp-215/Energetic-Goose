"""Evaluation pipeline tests. Everything runs in mock mode (no inference calls)
against a temporary data directory, so no key and no Neo4j are needed."""

import json
from collections import Counter

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_MOCK", "1")
    monkeypatch.setenv("EVAL_DATA_DIR", str(tmp_path))
    from app.core import graph as graph_mod
    from app.core import store as store_mod
    from app.main import app

    store_mod.sessions.reset_cache()
    store_mod.personas.reset_cache()
    graph_mod.reset_graph_for_tests(graph_mod.MemoryGraphStore(tmp_path / "graph.json"))
    yield TestClient(app)
    graph_mod.reset_graph_for_tests(None)
    store_mod.sessions.reset_cache()
    store_mod.personas.reset_cache()


def _run(client, models, **overrides):
    payload = {"models": models, "items_per_benchmark": 3, "agent_turns": 2, **overrides}
    with client.stream("POST", "/api/eval/run/stream", json=payload) as response:
        assert response.status_code == 200
        return [json.loads(line) for line in response.iter_lines() if line]


# --- graders -----------------------------------------------------------------

def test_letter_and_number_extraction():
    from app.core.benchmarks import extract_letter, extract_number

    assert extract_letter("B", 4) == "B"
    assert extract_letter("The answer is (C).", 4) == "C"
    assert extract_letter("Answer: D because ...", 4) == "D"
    assert extract_letter("I think A) is right", 4) == "A"
    assert extract_letter("E", 4) is None  # outside the choice range
    assert extract_number("so 12 + 30 = 42\n#### 42") == 42.0
    assert extract_number("The total is $1,250.50.") == 1250.5
    assert extract_number("no digits here") is None


def test_feedback_scoring_weights():
    from app.core.agents import parse_feedback, score_feedback

    fb = parse_feedback('{"ratings": {"helpfulness": 10, "accuracy": 2, "clarity": 6, '
                        '"tone": 6, "trust": 6}, "would_use_again": true, "summary": "ok"}')
    assert fb is not None
    accuracy_first = {"helpfulness": 0.1, "accuracy": 0.6, "clarity": 0.1, "tone": 0.1, "trust": 0.1}
    helpful_first = {"helpfulness": 0.6, "accuracy": 0.1, "clarity": 0.1, "tone": 0.1, "trust": 0.1}
    assert score_feedback(fb["ratings"], accuracy_first) < score_feedback(fb["ratings"], helpful_first)
    assert parse_feedback("not json at all") is None


# --- personas ----------------------------------------------------------------

def test_default_personas_seeded(client):
    body = client.get("/api/eval/personas").json()
    ids = {p["id"] for p in body["personas"]}
    assert ids == {"maya-chen", "prof-whitfield", "li-wei", "priya-nair", "rose-kowalski"}
    assert all(abs(sum(p["priorities"].values()) - 1) < 0.01 for p in body["personas"])


def test_import_update_delete_persona(client):
    payload = [{
        "name": "Diego Ramirez",
        "personality_traits": ["friendly"],
        "priorities": {"clarity": 2, "tone": 2},
        "scenario": {"title": "Email", "opening_message": "Help me write an email to a supplier."},
    }]
    body = client.post("/api/eval/personas/import", json=payload).json()
    assert body["imported"] == ["diego-ramirez"]
    diego = client.get("/api/eval/personas/diego-ramirez").json()
    assert diego["priorities"]["clarity"] == pytest.approx(0.5)
    assert diego["builtin"] is False

    diego["patience"] = 9
    updated = client.put("/api/eval/personas/diego-ramirez", json=diego).json()
    assert updated["patience"] == 9

    assert client.delete("/api/eval/personas/diego-ramirez").json() == {"deleted": "diego-ramirez"}
    assert client.get("/api/eval/personas/diego-ramirez").status_code == 404


def test_import_rejects_invalid_persona(client):
    response = client.post("/api/eval/personas/import", json=[{"name": "no scenario"}])
    assert response.status_code == 422


# --- sessions ----------------------------------------------------------------

def test_stream_events_and_scoring(client):
    events = _run(client, ["vendor-a/model-x"])
    names = Counter(e["event"] for e in events)
    assert names["session_created"] == 1
    assert names["session_done"] == 1
    assert names["benchmark_result"] == 5
    assert names["agent_feedback"] == 5
    assert names["agent_turn"] == 5 * 4  # 2 user turns + 2 replies per agent
    assert events[-1]["event"] == "all_done"

    session = next(e for e in events if e["event"] == "session_done")["session"]
    assert session["status"] == "done"
    w = session["weights"]
    expected = round(w["benchmark"] * session["benchmark_score"]
                     + w["agents"] * session["agent_score"], 2)
    assert session["final_score"] == pytest.approx(expected, abs=0.01)
    assert len(session["agents"]) == 5
    assert all(a["feedback"]["ratings"].keys() >= {"helpfulness", "trust"} for a in session["agents"])

    # persisted and retrievable
    fetched = client.get(f"/api/eval/sessions/{session['id']}").json()
    assert fetched["final_score"] == session["final_score"]


def test_custom_weights_and_agent_subset(client):
    events = _run(client, ["vendor-a/model-x"], benchmark_weight=1.0,
                  agent_ids=["maya-chen", "rose-kowalski"], benchmarks=["mmlu", "gsm8k"])
    session = next(e for e in events if e["event"] == "session_done")["session"]
    assert session["weights"] == {"benchmark": 1.0, "agents": 0.0}
    assert session["final_score"] == session["benchmark_score"]
    assert [a["agent_id"] for a in session["agents"]] and len(session["agents"]) == 2
    assert {b["name"] for b in session["benchmarks"]} == {"mmlu", "gsm8k"}


def test_unknown_persona_or_benchmark_rejected(client):
    bad = client.post("/api/eval/run/stream", json={"models": ["m"], "agent_ids": ["nobody"]})
    assert bad.status_code == 422
    bad = client.post("/api/eval/run/stream", json={"models": ["m"], "benchmarks": ["nope"]})
    assert bad.status_code == 422


def test_graph_rankings_and_delete(client):
    _run(client, ["vendor-a/model-x", "vendor-b/model-y"])
    _run(client, ["vendor-a/model-x"])

    sessions = client.get("/api/eval/sessions").json()["sessions"]
    assert len(sessions) == 3
    rankings = client.get("/api/eval/rankings").json()["rankings"]
    assert [r["rank"] for r in rankings] == [1, 2]
    by_model = {r["model"]: r for r in rankings}
    assert by_model["vendor-a/model-x"]["sessions"] == 2
    assert by_model["vendor-b/model-y"]["sessions"] == 1

    sid = sessions[0]["id"]
    graph = client.get(f"/api/eval/sessions/{sid}/graph").json()
    assert graph["backend"] == "memory"
    labels = Counter(n["label"] for n in graph["nodes"])
    assert labels["Session"] == 1 and labels["Model"] == 1
    assert labels["Agent"] == 5 and labels["Feedback"] == 5 and labels["Benchmark"] == 5
    assert labels["Turn"] == 5 * 4
    types = Counter(r["type"] for r in graph["relationships"])
    assert types["EVALUATES"] == 1 and types["INTERACTED_WITH"] == 5 and types["GAVE"] == 5
    # every relationship endpoint is in the returned node set
    ids = {n["id"] for n in graph["nodes"]}
    assert all(r["from"] in ids and r["to"] in ids for r in graph["relationships"])

    assert client.delete(f"/api/eval/sessions/{sid}").json()["deleted"] == sid
    assert client.get(f"/api/eval/sessions/{sid}").status_code == 404
    assert client.get(f"/api/eval/sessions/{sid}/graph").status_code == 404
    assert len(client.get("/api/eval/sessions").json()["sessions"]) == 2
    status = client.get("/api/eval/graph/status").json()
    assert status["labels"]["Session"] == 2


def test_cypher_requires_neo4j(client):
    response = client.post("/api/eval/graph/cypher", json={"query": "MATCH (n) RETURN n"})
    assert response.status_code == 409


def test_papers_graph_requires_neo4j(client):
    response = client.get("/api/eval/graph/papers")
    assert response.status_code == 409
    assert "Neo4j" in response.json()["detail"]


def test_meta(client):
    body = client.get("/api/eval/meta").json()
    assert body["mock_mode"] is True
    assert body["graph"]["backend"] == "memory"
    assert {b["name"] for b in body["benchmarks"]} >= {"mmlu", "gsm8k", "arc_challenge"}
    assert any(m["region"] == "CN" for m in body["catalog"])
    assert any(m["region"] == "US" for m in body["catalog"])


# --- progress, ETA, tokens ---------------------------------------------------

def test_progress_events_and_token_accounting(client):
    events = _run(client, ["vendor-a/model-x"], agent_ids=["maya-chen", "priya-nair"],
                  benchmarks=["mmlu", "gsm8k"])
    progress = [e for e in events if e["event"] == "progress"]
    assert progress, "progress events should be emitted"
    # monotonic percent, ends at 100 with the three stages done
    pcts = [p["percent"] for p in progress]
    assert pcts == sorted(pcts)
    last = progress[-1]
    assert last["percent"] == 100.0
    assert last["stage"] == "done"
    assert {s["status"] for s in last["stages"].values()} == {"done"}
    # units: 3 items x 2 benchmarks + 2 agents x (2 turns x 2 calls)
    assert last["units_total"] == 6 + 2 * 4
    assert last["units_done"] == last["units_total"]
    assert last["eta_s"] == 0.0
    # an ETA exists once the first benchmark item is in
    mid = next(p for p in progress if p["stages"]["benchmarks"]["done"] >= 1)
    assert mid["eta_s"] is not None and mid["eta_s"] >= 0
    # running token totals are non-decreasing and split by stage
    totals = [p["tokens"]["total"] for p in progress]
    assert totals == sorted(totals) and totals[-1] > 0
    assert last["tokens_by_stage"]["benchmarks"]["total"] > 0
    assert last["tokens_by_stage"]["agents"]["target"]["total"] > 0
    assert last["tokens_by_stage"]["agents"]["simulator"]["total"] > 0

    session = next(e for e in events if e["event"] == "session_done")["session"]
    tok = session["tokens"]
    assert tok["total"]["total"] == (
        tok["benchmarks"]["total"] + tok["agents"]["target"]["total"] + tok["agents"]["simulator"]["total"]
    )
    assert set(tok["per_agent"]) == {"maya-chen", "priya-nair"}
    assert set(tok["per_benchmark"]) == {"mmlu", "gsm8k"}
    assert session["timings"]["total_s"] >= 0
    for agent in session["agents"]:
        # each turn is attributed to who spent the tokens
        assert agent["turns"][0]["by"] == "script" and agent["turns"][0]["tokens"]["total"] == 0
        assert {t["by"] for t in agent["turns"][1:]} <= {"target", "simulator"}
        # per-round roll-up matches the turns
        assert [r["round"] for r in agent["rounds"]] == [1, 2]
        assert sum(r["total_tokens"] for r in agent["rounds"]) == (
            agent["tokens"]["target"]["total"] + agent["tokens"]["simulator"]["total"]
            - agent["tokens"]["feedback"]["total"]
        )
        assert agent["tokens"]["feedback"]["total"] > 0
    # summaries carry percent + tokens for the sessions table
    summary = client.get("/api/eval/sessions").json()["sessions"][0]
    assert summary["percent"] == 100.0 and summary["total_tokens"] == tok["total"]["total"]


def test_probe_models(client):
    body = client.post("/api/eval/models/probe", json={"models": ["a/one", "b/two"]}).json()
    assert body["accessible"] == ["a/one", "b/two"]
    assert all(r["latency_ms"] >= 0 and r["tokens"]["total"] > 0 for r in body["results"])


def test_feedback_salvage_from_truncated_json():
    from app.core.agents import parse_feedback

    truncated = '```json\n{\n  "ratings": {\n    "helpfulness": 9,\n    "accuracy": 8,\n    "clarity": 7,\n    "tone": 9,\n    "trust": 8\n  },\n  "would_use_again": true,\n  "summary": "It answered fast and'
    fb = parse_feedback(truncated)
    assert fb is not None
    assert fb["ratings"] == {"helpfulness": 9, "accuracy": 8, "clarity": 7, "tone": 9, "trust": 8}
    assert fb["would_use_again"] is True
    assert fb["summary"].startswith("It answered fast")
    assert parse_feedback('garbage "helpfulness": 9 garbage') is None  # too little to salvage
