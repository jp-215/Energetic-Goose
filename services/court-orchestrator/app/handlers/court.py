"""Court business logic: both counsels deliberate concurrently, then the judge rules."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import asdict
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import HTTPException

from ..core.canopy import ModelCallResult, call_role_model
from ..core.config import ROLE_INSTRUCTIONS
from ..models.case import CaseRequest, CaseResponse


def _case_prompt(title: str, context: str, query: str) -> str:
    parts = [f"Case Title: {title}"]
    if context.strip():
        parts.append(f"Case Facts / Context:\n{context.strip()}")
    if query.strip():
        parts.append(f"Question before the court:\n{query.strip()}")
    return "\n\n".join(parts)


def _judge_prompt(title: str, context: str, query: str,
                  simple: ModelCallResult, complex_: ModelCallResult) -> str:
    def opinion_block(label: str, result: ModelCallResult) -> str:
        if result.status != "ok":
            return f"{label}: UNAVAILABLE (error: {result.error})"
        return (
            f"{label} (model {result.model}):\n"
            f"  verdict: {result.verdict}\n"
            f"  confidence: {result.confidence}\n"
            f"  rationale: {result.rationale or result.answer}"
        )

    return (
        _case_prompt(title, context, query)
        + "\n\n--- Counsel Opinions ---\n\n"
        + opinion_block("Simple Counsel", simple)
        + "\n\n"
        + opinion_block("Complex Counsel", complex_)
        + "\n\nIssue your final ruling."
    )


async def run_case(
    title: str,
    context: str,
    query: str,
    model_overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Run one case through the full court: simple + complex in parallel, then judge."""
    overrides = model_overrides or {}
    case_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()

    counsel_prompt = _case_prompt(title, context, query)
    simple_result, complex_result = await asyncio.gather(
        call_role_model("simple", ROLE_INSTRUCTIONS["simple"], counsel_prompt,
                        overrides.get("simple")),
        call_role_model("complex", ROLE_INSTRUCTIONS["complex"], counsel_prompt,
                        overrides.get("complex")),
    )

    judge_result = await call_role_model(
        "judge",
        ROLE_INSTRUCTIONS["judge"],
        _judge_prompt(title, context, query, simple_result, complex_result),
        overrides.get("judge"),
    )

    total_latency_ms = int((time.perf_counter() - started) * 1000)
    roles = {"simple": simple_result, "complex": complex_result, "judge": judge_result}
    return _build_response(case_id, title, roles, total_latency_ms)


def _build_response(case_id: str, title: str, roles: Dict[str, ModelCallResult],
                    total_latency_ms: int) -> Dict[str, Any]:
    judge_result = roles["judge"]
    errors = [f"{role}: {r.error}" for role, r in roles.items() if r.status == "error"]
    return {
        "case_id": case_id,
        "title": title,
        "final_verdict": judge_result.verdict,
        "judge_rationale": judge_result.rationale or judge_result.answer,
        "roles": {role: asdict(result) for role, result in roles.items()},
        "total_latency_ms": total_latency_ms,
        "total_retries": sum(r.retries_used for r in roles.values()),
        "status": "error" if judge_result.status == "error" else "ok",
        "error": "; ".join(errors) if errors else None,
    }


async def run_case_events(
    title: str,
    context: str,
    query: str,
    model_overrides: Optional[Dict[str, str]] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Event-driven court run: yields one event per stage the moment it happens.

    Order: case_accepted -> role_result (each counsel, as it finishes) ->
    judge_started -> role_result (judge) -> case_closed.
    """
    overrides = model_overrides or {}
    case_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    yield {"event": "case_accepted", "case_id": case_id, "title": title}

    counsel_prompt = _case_prompt(title, context, query)
    counsel_tasks = [
        asyncio.create_task(
            call_role_model(role, ROLE_INSTRUCTIONS[role], counsel_prompt, overrides.get(role))
        )
        for role in ("simple", "complex")
    ]

    roles: Dict[str, ModelCallResult] = {}
    for task in asyncio.as_completed(counsel_tasks):
        result = await task
        roles[result.role] = result
        yield {"event": "role_result", "role": result.role, "result": asdict(result)}

    yield {"event": "judge_started"}
    judge_result = await call_role_model(
        "judge",
        ROLE_INSTRUCTIONS["judge"],
        _judge_prompt(title, context, query, roles["simple"], roles["complex"]),
        overrides.get("judge"),
    )
    roles["judge"] = judge_result
    yield {"event": "role_result", "role": "judge", "result": asdict(judge_result)}

    total_latency_ms = int((time.perf_counter() - started) * 1000)
    yield {"event": "case_closed", "response": _build_response(case_id, title, roles, total_latency_ms)}


def validate_overrides(case: CaseRequest) -> None:
    if case.model_overrides:
        invalid_roles = set(case.model_overrides) - set(ROLE_INSTRUCTIONS)
        if invalid_roles:
            raise HTTPException(status_code=422, detail=f"Unknown roles: {sorted(invalid_roles)}")


async def handle_run(case: CaseRequest) -> CaseResponse:
    """Validate the request's business rules, then run the court."""
    validate_overrides(case)
    result = await run_case(case.title, case.context, case.query, case.model_overrides)
    return CaseResponse(**result)
