import asyncio

import app.handlers.court as court
from app.core.canopy import ModelCallResult


def make_result(role: str, verdict: str = "MIXED", status: str = "ok",
                error: str | None = None, retries: int = 0) -> ModelCallResult:
    return ModelCallResult(
        role=role,
        model=f"test/{role}-model",
        answer=f'{{"verdict": "{verdict}"}}',
        verdict=verdict,
        confidence=0.8 if status == "ok" else None,
        rationale=f"{role} rationale",
        latency_ms=5,
        retries_used=retries,
        status=status,
        error=error,
    )


def run_with_stub(monkeypatch, results: dict, capture_prompts: dict | None = None):
    async def fake_call(role, instruction, prompt, override=None):
        if capture_prompts is not None:
            capture_prompts[role] = prompt
        return results[role]

    monkeypatch.setattr(court, "call_role_model", fake_call)
    return asyncio.run(court.run_case("Test Case", "some facts", "who wins?"))


def test_run_case_happy_path(monkeypatch):
    prompts: dict = {}
    result = run_with_stub(
        monkeypatch,
        {
            "simple": make_result("simple", "PLAINTIFF"),
            "complex": make_result("complex", "DEFENDANT"),
            "judge": make_result("judge", "MIXED"),
        },
        prompts,
    )
    assert result["status"] == "ok"
    assert result["final_verdict"] == "MIXED"
    assert result["judge_rationale"] == "judge rationale"
    assert set(result["roles"]) == {"simple", "complex", "judge"}
    assert result["error"] is None
    # The judge must actually see both counsel opinions.
    assert "Simple Counsel" in prompts["judge"]
    assert "Complex Counsel" in prompts["judge"]
    assert "PLAINTIFF" in prompts["judge"]
    assert "DEFENDANT" in prompts["judge"]
    # Counsels see the case, not each other.
    assert "Counsel Opinions" not in prompts["simple"]


def test_run_case_counsel_failure_is_survivable(monkeypatch):
    result = run_with_stub(
        monkeypatch,
        {
            "simple": make_result("simple", "UNKNOWN", status="error", error="boom", retries=3),
            "complex": make_result("complex", "PLAINTIFF"),
            "judge": make_result("judge", "PLAINTIFF"),
        },
    )
    assert result["status"] == "ok"  # judge still ruled
    assert result["final_verdict"] == "PLAINTIFF"
    assert "simple: boom" in result["error"]
    assert result["total_retries"] == 3


def test_run_case_judge_failure_is_terminal(monkeypatch):
    result = run_with_stub(
        monkeypatch,
        {
            "simple": make_result("simple", "PLAINTIFF"),
            "complex": make_result("complex", "PLAINTIFF"),
            "judge": make_result("judge", "UNKNOWN", status="error", error="timeout"),
        },
    )
    assert result["status"] == "error"
    assert "judge: timeout" in result["error"]
