import app.handlers.court as court_handler
from app.main import app
from fastapi.testclient import TestClient


def stub_run_case(monkeypatch):
    async def fake_run_case(title, context, query, overrides=None):
        return {
            "case_id": "abc123def456",
            "title": title,
            "final_verdict": "MIXED",
            "judge_rationale": "split the difference",
            "roles": {
                role: {
                    "role": role,
                    "model": (overrides or {}).get(role, f"default/{role}"),
                    "answer": "{}",
                    "verdict": "MIXED",
                    "confidence": 0.5,
                    "rationale": "r",
                    "latency_ms": 1,
                    "retries_used": 0,
                    "status": "ok",
                    "error": None,
                }
                for role in ("simple", "complex", "judge")
            },
            "total_latency_ms": 3,
            "total_retries": 0,
            "status": "ok",
            "error": None,
        }

    monkeypatch.setattr(court_handler, "run_case", fake_run_case)


def test_health():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["service"] == "court-orchestrator"


def test_court_run(monkeypatch):
    stub_run_case(monkeypatch)
    client = TestClient(app)
    response = client.post("/api/court/run", json={"title": "T", "context": "c", "query": "q"})
    assert response.status_code == 200
    body = response.json()
    assert body["final_verdict"] == "MIXED"
    assert body["roles"]["judge"]["model"] == "default/judge"


def test_court_run_with_override(monkeypatch):
    stub_run_case(monkeypatch)
    client = TestClient(app)
    response = client.post(
        "/api/court/run",
        json={"title": "T", "model_overrides": {"judge": "minimax/minimax-m3"}},
    )
    assert response.status_code == 200
    assert response.json()["roles"]["judge"]["model"] == "minimax/minimax-m3"


def test_court_run_rejects_unknown_role():
    client = TestClient(app)
    response = client.post(
        "/api/court/run",
        json={"title": "T", "model_overrides": {"prosecutor": "foo"}},
    )
    assert response.status_code == 422


def test_court_run_requires_title():
    client = TestClient(app)
    response = client.post("/api/court/run", json={"context": "no title"})
    assert response.status_code == 422


def test_court_run_stream_event_order(monkeypatch):
    import json

    from app.core.canopy import ModelCallResult
    from app.models.case import CaseResponse

    async def fake_call(role, instruction, prompt, override=None):
        return ModelCallResult(
            role=role,
            model=f"test/{role}-model",
            answer="{}",
            verdict="MIXED",
            confidence=0.5,
            rationale="r",
            latency_ms=1,
            retries_used=0,
            status="ok",
        )

    monkeypatch.setattr(court_handler, "call_role_model", fake_call)
    client = TestClient(app)
    with client.stream(
        "POST", "/api/court/run/stream", json={"title": "T", "context": "c", "query": "q"}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-ndjson")
        events = [json.loads(line) for line in response.iter_lines() if line]

    names = [e["event"] for e in events]
    assert names[0] == "case_accepted"
    assert names[-1] == "case_closed"
    assert "judge_started" in names
    assert names.count("role_result") == 3
    # Counsels report before the judge is even seated.
    counsel_roles = {e["role"] for e in events if e["event"] == "role_result"}
    assert counsel_roles == {"simple", "complex", "judge"}
    assert names.index("judge_started") > max(
        i for i, e in enumerate(events) if e["event"] == "role_result" and e["role"] != "judge"
    )
    # The closing event carries the full non-streaming response shape.
    CaseResponse(**events[-1]["response"])


def test_court_run_stream_rejects_unknown_role():
    client = TestClient(app)
    response = client.post(
        "/api/court/run/stream",
        json={"title": "T", "model_overrides": {"bailiff": "foo"}},
    )
    assert response.status_code == 422
