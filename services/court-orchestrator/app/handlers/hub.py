"""Coding Hub business logic.

Lifecycle (every step is emitted as a trace event so the UI can show it):

    brief -> planner (analysis, team size, task assignment)
          -> engineer agents build concurrently
               -> an agent may summon one helper for a sub-task (capped)
          -> integrator makes the workspace runnable
          -> workspace (files) + full trace
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from fastapi import HTTPException

from ..core.canopy import ChatCallResult, _extract_json_object, call_chat
from ..core.config import HUB_INFERENCE_CONFIG, HUB_LIMITS, HUB_ROLE_INSTRUCTIONS, get_hub_models
from ..core.workspace import WorkspaceError, publish_workspace, safe_relative_path, write_workspace
from ..models.hub import (
    AgentResult,
    AgentSpec,
    CallTrace,
    ExportRequest,
    ExportResponse,
    HelpRequest,
    HubRequest,
    HubResponse,
    HubRolesResponse,
    IntegrationResult,
    PlanResponse,
    PublishRequest,
    PublishResponse,
    TaskSpec,
    TeamPlan,
    WorkspaceFile,
)

# ---- Output format shared by engineers and the integrator -------------------

OUTPUT_FORMAT = """Respond ONLY in this exact sectioned format (no markdown fences around files):

=== SUMMARY ===
<2-4 sentences: what you built and any decisions you made>
=== FILE: relative/path/to/file.ext ===
<complete raw file content>
=== END FILE ===
(repeat the FILE / END FILE pair for every file you produce)
=== NOTES ===
<interfaces, assumptions, and anything teammates or the integrator must know>
=== HELP ===
NONE
"""

HELP_FORMAT = """If — and only if — a clearly separable sub-task needs a specialist, replace NONE
under === HELP === with exactly these three lines:
role: <helper's role, e.g. "Test Engineer">
task: <precise, self-contained description of the sub-task and expected files>
reason: <why you cannot finish it yourself>
"""

INTEGRATOR_FORMAT = """Respond ONLY in this exact sectioned format (no markdown fences around files):

=== SUMMARY ===
<2-4 sentences: what was missing or broken and what you changed>
=== RUN ===
<exact shell commands to install dependencies, run the tests, and run the project>
=== FILE: relative/path/to/file.ext ===
<complete raw file content>
=== END FILE ===
(repeat the FILE / END FILE pair for every file you add or change; emit complete files only)
=== NOTES ===
<anything the user must know>
"""

SECTION_RE = re.compile(r"^=== (SUMMARY|NOTES|HELP|RUN|END FILE|FILE: .+?) ===[ \t]*$", re.M)
FENCE_RE = re.compile(r"^```[^\n]*\n(.*?)\n```\s*$", re.S)
MAX_FILE_CHARS_FOR_INTEGRATOR = 6000
MAX_TOTAL_CHARS_FOR_INTEGRATOR = 60000

PLANNER_FORMAT = """Return STRICT JSON only, no prose before or after, with this shape:
{
  "analysis": "<what the brief asks for, key constraints, risks>",
  "team_size": <integer, 1..MAX>,
  "rationale": "<why this many agents and this split>",
  "agents": [
    {
      "id": "agent-1",
      "name": "<short name>",
      "role": "<e.g. Backend Engineer>",
      "specialty": "<one line>",
      "tasks": [
        {"id": "t1", "title": "<short>", "description": "<what to build, concretely>",
         "deliverables": ["relative/path/one.py", "relative/path/two.py"]}
      ]
    }
  ],
  "integration_notes": "<how the pieces fit: entrypoint, shared interfaces, run command>"
}
Every task must belong to exactly one agent. Deliverables are file paths relative to the
project root. Choose ONE language/stack and keep the whole project consistent."""


# ---- Prompt builders ---------------------------------------------------------


def _brief_block(brief: HubRequest) -> str:
    parts = [f"Project: {brief.title}"]
    if brief.context.strip():
        parts.append(f"Context:\n{brief.context.strip()}")
    if brief.goal.strip():
        parts.append(f"Goal / deliverable:\n{brief.goal.strip()}")
    return "\n\n".join(parts)


def _planner_prompt(brief: HubRequest, max_agents: int) -> str:
    return (
        _brief_block(brief)
        + f"\n\nMaximum team size: {max_agents}.\n\n"
        + PLANNER_FORMAT.replace("MAX", str(max_agents))
    )


def _tasks_block(agent: AgentSpec) -> str:
    lines = []
    for task in agent.tasks:
        lines.append(f"- [{task.id}] {task.title}: {task.description}")
        if task.deliverables:
            lines.append(f"    deliverables: {', '.join(task.deliverables)}")
    return "\n".join(lines) or "- (none listed — use your judgement)"


def _teammates_block(plan: TeamPlan, agent: AgentSpec) -> str:
    lines = []
    for other in plan.agents:
        if other.id == agent.id or other.parent_id:
            continue
        files = [d for t in other.tasks for d in t.deliverables]
        lines.append(f"- {other.name} ({other.role}): {', '.join(files) or 'no files listed'}")
    return "\n".join(lines) or "- (you are the only engineer)"


def _agent_prompt(brief: HubRequest, plan: TeamPlan, agent: AgentSpec) -> str:
    return (
        _brief_block(brief)
        + f"\n\nPlanner analysis:\n{plan.analysis}\n\n"
        + f"Integration notes (respect these interfaces):\n{plan.integration_notes or '(none)'}\n\n"
        + f"You are {agent.name} — {agent.role}. Specialty: {agent.specialty or 'general'}.\n"
        + f"Your tasks:\n{_tasks_block(agent)}\n\n"
        + f"Teammates and the files they own (do not write those files):\n{_teammates_block(plan, agent)}\n\n"
        + OUTPUT_FORMAT
        + "\n"
        + HELP_FORMAT
    )


def _helper_prompt(brief: HubRequest, plan: TeamPlan, helper: AgentSpec,
                   parent: AgentSpec, parent_result: AgentResult) -> str:
    parent_files = ", ".join(f.path for f in parent_result.files) or "(none)"
    return (
        _brief_block(brief)
        + f"\n\nPlanner analysis:\n{plan.analysis}\n\n"
        + f"Integration notes:\n{plan.integration_notes or '(none)'}\n\n"
        + f"You are {helper.name} — {helper.role}, summoned by {parent.name} ({parent.role}).\n"
        + f"Why you were summoned: {helper.summoned_reason}\n\n"
        + f"{parent.name} has already produced: {parent_files}\n"
        + f"{parent.name}'s summary: {parent_result.summary}\n"
        + f"{parent.name}'s notes: {parent_result.notes or '(none)'}\n\n"
        + f"Your sub-task:\n{_tasks_block(helper)}\n\n"
        + "Do not rewrite your summoner's files unless the sub-task requires it.\n\n"
        + OUTPUT_FORMAT
        + "\nYou may NOT summon further helpers; leave HELP as NONE.\n"
    )


def _integrator_prompt(brief: HubRequest, plan: TeamPlan, results: List[AgentResult],
                       workspace: Dict[str, WorkspaceFile]) -> str:
    report = []
    for result in results:
        spec_line = f"- {result.agent_id} [{result.status}]: {result.summary or '(no summary)'}"
        if result.notes:
            spec_line += f"\n    notes: {result.notes}"
        report.append(spec_line)

    budget = MAX_TOTAL_CHARS_FOR_INTEGRATOR
    file_blocks = []
    for path in sorted(workspace):
        content = workspace[path].content
        if len(content) > MAX_FILE_CHARS_FOR_INTEGRATOR:
            content = content[:MAX_FILE_CHARS_FOR_INTEGRATOR] + "\n... [truncated]"
        block = f"--- {path} (by {workspace[path].author}) ---\n{content}"
        if budget - len(block) < 0:
            file_blocks.append(f"--- {path} (by {workspace[path].author}) --- [omitted: budget]")
            continue
        budget -= len(block)
        file_blocks.append(block)

    return (
        _brief_block(brief)
        + f"\n\nPlanner analysis:\n{plan.analysis}\n\n"
        + f"Integration notes:\n{plan.integration_notes or '(none)'}\n\n"
        + "Agent reports:\n" + "\n".join(report) + "\n\n"
        + "Current workspace files:\n\n" + "\n\n".join(file_blocks) + "\n\n"
        + "Produce ONLY the files that are missing or must change to make the project run "
        + "(README.md with setup/run steps is required; add a dependency manifest and "
        + "entrypoint if absent). Existing files you do not emit are kept as-is.\n\n"
        + INTEGRATOR_FORMAT
    )


# ---- Parsers -----------------------------------------------------------------


def _strip_fence(body: str) -> str:
    match = FENCE_RE.match(body.strip())
    return match.group(1) if match else body


def parse_sectioned_output(text: str) -> Dict[str, Any]:
    """Parse the === SECTION === format into summary/notes/files/help/run."""
    result: Dict[str, Any] = {"summary": "", "notes": "", "files": [], "help": None, "run": ""}
    text = text or ""
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        result["summary"] = text.strip()[:2000]
        return result

    for index, match in enumerate(matches):
        header = match.group(1)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip("\n")
        if header == "SUMMARY":
            result["summary"] = body.strip()
        elif header == "NOTES":
            result["notes"] = body.strip()
        elif header == "RUN":
            result["run"] = _strip_fence(body).strip()
        elif header == "HELP":
            result["help"] = _parse_help(body)
        elif header.startswith("FILE: "):
            path = header[len("FILE: "):].strip().strip("`")
            terminated = index + 1 < len(matches)  # some header follows; the block was closed
            result["files"].append({
                "path": path,
                "content": _strip_fence(body).rstrip() + "\n",
                "complete": terminated,
            })
    return result


def _parse_help(body: str) -> Optional[Dict[str, str]]:
    cleaned = body.strip()
    if not cleaned or cleaned.upper().startswith("NONE"):
        return None
    fields: Dict[str, str] = {}
    for line in cleaned.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip().lower()
            if key in ("role", "task", "reason"):
                fields[key] = value.strip()
    if fields.get("task"):
        fields.setdefault("role", "Helper Engineer")
        fields.setdefault("reason", "")
        return fields
    return None


def parse_plan(text: str, max_agents: int) -> Tuple[Optional[TeamPlan], Optional[str]]:
    """Turn the planner's JSON into a validated TeamPlan (or explain why not)."""
    payload = _extract_json_object(text or "")
    if not payload:
        return None, "planner did not return a JSON object"

    raw_agents = payload.get("agents") or []
    agents: List[AgentSpec] = []
    seen_ids: set = set()
    for index, raw in enumerate(raw_agents[:max_agents], start=1):
        if not isinstance(raw, dict):
            continue
        agent_id = str(raw.get("id") or f"agent-{index}").strip() or f"agent-{index}"
        if agent_id in seen_ids:
            agent_id = f"{agent_id}-{index}"
        seen_ids.add(agent_id)
        tasks = []
        for t_index, raw_task in enumerate(raw.get("tasks") or [], start=1):
            if not isinstance(raw_task, dict):
                continue
            deliverables = [str(d) for d in (raw_task.get("deliverables") or []) if str(d).strip()]
            tasks.append(TaskSpec(
                id=str(raw_task.get("id") or f"{agent_id}-t{t_index}"),
                title=str(raw_task.get("title") or f"Task {t_index}"),
                description=str(raw_task.get("description") or ""),
                deliverables=deliverables,
            ))
        agents.append(AgentSpec(
            id=agent_id,
            name=str(raw.get("name") or f"Agent {index}"),
            role=str(raw.get("role") or "Engineer"),
            specialty=str(raw.get("specialty") or ""),
            tasks=tasks,
        ))

    if not agents:
        return None, "planner proposed no agents"

    return TeamPlan(
        analysis=str(payload.get("analysis") or ""),
        team_size=len(agents),
        rationale=str(payload.get("rationale") or ""),
        agents=agents,
        integration_notes=str(payload.get("integration_notes") or ""),
    ), None


def fallback_plan(brief: HubRequest, reason: str) -> TeamPlan:
    """Single generalist agent when the planner cannot be parsed — the run still proceeds,
    and the trace says why."""
    return TeamPlan(
        analysis=f"Planner output unusable ({reason}); falling back to one generalist engineer.",
        team_size=1,
        rationale="Fallback: a single agent implements the whole brief.",
        agents=[AgentSpec(
            id="agent-1", name="Generalist", role="Full-stack Engineer",
            specialty="end-to-end implementation",
            tasks=[TaskSpec(id="t1", title="Implement the brief",
                            description=brief.goal or brief.context or brief.title)],
        )],
        integration_notes="",
        fallback=True,
    )


# ---- Helpers -----------------------------------------------------------------


def _trace(call: ChatCallResult) -> CallTrace:
    return CallTrace(
        role=call.role, model=call.model, system_prompt=call.system_prompt,
        user_prompt=call.user_prompt, raw_output=call.text, latency_ms=call.latency_ms,
        retries_used=call.retries_used, status=call.status, error=call.error,
        prompt_tokens=call.prompt_tokens, completion_tokens=call.completion_tokens,
        finish_reason=call.finish_reason,
    )


def _files_from(parsed: Dict[str, Any], author: str, limit: int,
                truncated: bool = False) -> Tuple[List[WorkspaceFile], List[Tuple[str, str]]]:
    """Validate agent-written files. Returns (accepted, [(path, reason) rejected])."""
    files: List[WorkspaceFile] = []
    rejected: List[Tuple[str, str]] = []
    for raw in parsed.get("files", [])[:limit]:
        try:
            path = safe_relative_path(raw["path"]).as_posix()
        except WorkspaceError:
            rejected.append((str(raw.get("path")), "unsafe path"))
            continue
        if truncated and not raw.get("complete", True):
            rejected.append((path, "incomplete: model output hit max_tokens mid-file"))
            continue
        files.append(WorkspaceFile(path=path, content=raw["content"], author=author))
    return files, rejected


def _models(brief: HubRequest) -> Dict[str, str]:
    models = get_hub_models()
    for role, model in (brief.model_overrides or {}).items():
        if model:
            models[role] = model
    return models


def validate_overrides(brief: HubRequest) -> None:
    if brief.model_overrides:
        invalid = set(brief.model_overrides) - set(HUB_ROLE_INSTRUCTIONS)
        if invalid:
            raise HTTPException(status_code=422, detail=f"Unknown hub roles: {sorted(invalid)}")


# ---- Orchestration -----------------------------------------------------------


class _Run:
    """Mutable state for one run; events are pushed to a queue as they happen."""

    def __init__(self, brief: HubRequest):
        self.brief = brief
        self.run_id = uuid.uuid4().hex[:12]
        self.started = time.perf_counter()
        self.models = _models(brief)
        self.max_agents = brief.max_agents or HUB_LIMITS["max_team_size"]
        self.plan: Optional[TeamPlan] = None
        self.results: List[AgentResult] = []
        self.integration: Optional[IntegrationResult] = None
        self.workspace: Dict[str, WorkspaceFile] = {}
        self.helpers_used = 0
        self.total_calls = 0
        self.total_retries = 0
        self.queue: asyncio.Queue = asyncio.Queue()
        self.trace: List[Dict[str, Any]] = []

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started) * 1000)

    def emit(self, event: str, **payload: Any) -> None:
        record = {"event": event, "at_ms": self.elapsed_ms(), **payload}
        self.trace.append(record)
        self.queue.put_nowait(record)

    def account(self, call: ChatCallResult) -> None:
        self.total_calls += 1
        self.total_retries += call.retries_used

    def merge_files(self, files: List[WorkspaceFile], author: str) -> None:
        for f in files:
            previous = self.workspace.get(f.path)
            if previous and previous.author != author:
                self.emit("file_conflict", path=f.path, previous_author=previous.author,
                          new_author=author, resolution="latest write wins")
            self.workspace[f.path] = f


async def _run_planner(run: _Run) -> None:
    run.emit("planner_started", model=run.models["planner"], max_agents=run.max_agents)
    call = await call_chat(
        "planner", HUB_ROLE_INSTRUCTIONS["planner"], _planner_prompt(run.brief, run.max_agents),
        run.models["planner"], HUB_INFERENCE_CONFIG["planner_max_tokens"],
        HUB_INFERENCE_CONFIG["timeout_seconds"],
    )
    run.account(call)
    trace = _trace(call)
    if call.status != "ok":
        run.plan = fallback_plan(run.brief, f"planner call failed: {call.error}")
    else:
        plan, problem = parse_plan(call.text, run.max_agents)
        run.plan = plan or fallback_plan(run.brief, problem or "unknown")
    run.emit("plan_ready", plan=run.plan.model_dump(), call=trace.model_dump())


async def _run_agent(run: _Run, spec: AgentSpec, parent: Optional[Tuple[AgentSpec, AgentResult]] = None) -> None:
    assert run.plan is not None
    model = run.models["engineer"]
    run.emit("agent_started", agent=spec.model_dump(), model=model)

    if parent:
        prompt = _helper_prompt(run.brief, run.plan, spec, parent[0], parent[1])
    else:
        prompt = _agent_prompt(run.brief, run.plan, spec)
    call = await call_chat(
        "engineer", HUB_ROLE_INSTRUCTIONS["engineer"], prompt, model,
        HUB_INFERENCE_CONFIG["agent_max_tokens"], HUB_INFERENCE_CONFIG["timeout_seconds"],
    )
    run.account(call)

    parsed = parse_sectioned_output(call.text) if call.status == "ok" else {"files": []}
    truncated = call.finish_reason == "length"
    if truncated:
        run.emit("output_truncated", agent_id=spec.id, max_tokens=HUB_INFERENCE_CONFIG["agent_max_tokens"])
    files, rejected = _files_from(parsed, spec.id, HUB_LIMITS["max_files_per_agent"], truncated)
    for path, reason in rejected:
        run.emit("file_rejected", agent_id=spec.id, path=path, reason=reason)

    help_raw = parsed.get("help") if spec.depth < HUB_LIMITS["max_depth"] else None
    help_request = HelpRequest(**help_raw) if help_raw else None
    result = AgentResult(
        agent_id=spec.id, status=call.status, summary=parsed.get("summary", ""),
        notes=parsed.get("notes", ""), files=files, help_request=help_request, call=_trace(call),
    )
    run.results.append(result)
    run.merge_files(files, spec.id)

    if parsed.get("help") and spec.depth >= HUB_LIMITS["max_depth"]:
        run.emit("summon_denied", agent_id=spec.id, reason="helpers cannot summon helpers",
                 request=parsed["help"])
    elif help_request:
        if run.helpers_used >= HUB_LIMITS["max_helpers"]:
            run.emit("summon_denied", agent_id=spec.id,
                     reason=f"helper cap reached ({HUB_LIMITS['max_helpers']})",
                     request=help_request.model_dump())
        else:
            run.helpers_used += 1
            helper = AgentSpec(
                id=f"{spec.id}-helper", name=f"{spec.name}'s helper", role=help_request.role,
                specialty=help_request.role, parent_id=spec.id, depth=spec.depth + 1,
                summoned_reason=help_request.reason,
                tasks=[TaskSpec(id=f"{spec.id}-help", title=f"Assist {spec.name}",
                                description=help_request.task)],
            )
            result.helper_id = helper.id
            run.plan.agents.append(helper)
            run.emit("agent_summoned", agent=helper.model_dump(), parent_id=spec.id,
                     request=help_request.model_dump())

    run.emit("agent_result", agent_id=spec.id, result=result.model_dump())

    if result.helper_id:
        helper_spec = next(a for a in run.plan.agents if a.id == result.helper_id)
        await _run_agent(run, helper_spec, parent=(spec, result))


async def _run_integrator(run: _Run) -> None:
    assert run.plan is not None
    model = run.models["integrator"]
    run.emit("integration_started", model=model, file_count=len(run.workspace))
    call = await call_chat(
        "integrator", HUB_ROLE_INSTRUCTIONS["integrator"],
        _integrator_prompt(run.brief, run.plan, run.results, run.workspace), model,
        HUB_INFERENCE_CONFIG["integrator_max_tokens"], HUB_INFERENCE_CONFIG["timeout_seconds"],
    )
    run.account(call)
    parsed = parse_sectioned_output(call.text) if call.status == "ok" else {"files": []}
    truncated = call.finish_reason == "length"
    if truncated:
        run.emit("output_truncated", agent_id="integrator",
                 max_tokens=HUB_INFERENCE_CONFIG["integrator_max_tokens"])
    files, rejected = _files_from(parsed, "integrator", HUB_LIMITS["max_files_per_agent"] * 2,
                                  truncated)
    for path, reason in rejected:
        run.emit("file_rejected", agent_id="integrator", path=path, reason=reason)
    integration = IntegrationResult(
        status=call.status, summary=parsed.get("summary", ""),
        run_instructions=parsed.get("run", ""), files=files, call=_trace(call),
    )
    run.merge_files(files, "integrator")
    run.integration = integration
    run.emit("integration_result", result=integration.model_dump())


def _build_response(run: _Run) -> HubResponse:
    integration = run.integration
    failed_agents = [r.agent_id for r in run.results if r.status != "ok"]
    errors = []
    if failed_agents:
        errors.append(f"agents failed: {', '.join(failed_agents)}")
    if integration and integration.status != "ok":
        errors.append(f"integrator: {integration.call.error}")
    if run.results and all(r.status != "ok" for r in run.results):
        status = "error"
    elif not run.workspace:
        status = "error"
        errors.append("no files were produced")
    else:
        status = "ok"
    return HubResponse(
        run_id=run.run_id, title=run.brief.title, status=status, plan=run.plan,
        agents=run.results, integration=integration,
        workspace=[run.workspace[p] for p in sorted(run.workspace)],
        trace=[e for e in run.trace if e["event"] != "run_closed"],
        total_latency_ms=run.elapsed_ms(), total_calls=run.total_calls,
        total_retries=run.total_retries, error="; ".join(errors) or None,
    )


async def _orchestrate(run: _Run) -> None:
    """The full lifecycle; runs as a background task feeding run.queue."""
    try:
        await _run_planner(run)
        assert run.plan is not None
        run.emit("team_assembled", agent_ids=[a.id for a in run.plan.agents],
                 team_size=run.plan.team_size)
        await asyncio.gather(*(_run_agent(run, spec) for spec in list(run.plan.agents)))
        await _run_integrator(run)
        run.emit("run_closed", response=_build_response(run).model_dump())
    except Exception as exc:  # never leave the consumer hanging
        run.emit("error", detail=str(exc))
    finally:
        run.queue.put_nowait(None)


async def run_hub_events(brief: HubRequest) -> AsyncIterator[Dict[str, Any]]:
    run = _Run(brief)
    run.emit("run_accepted", run_id=run.run_id, title=brief.title, models=run.models,
             limits=HUB_LIMITS, max_agents=run.max_agents)
    worker = asyncio.create_task(_orchestrate(run))
    try:
        while True:
            item = await run.queue.get()
            if item is None:
                break
            yield item
    finally:
        if not worker.done():
            worker.cancel()


async def run_hub(brief: HubRequest) -> HubResponse:
    final: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    async for event in run_hub_events(brief):
        if event["event"] == "run_closed":
            final = event["response"]
        elif event["event"] == "error":
            error = event["detail"]
    if final is None:
        raise HTTPException(status_code=502, detail=error or "hub run produced no result")
    return HubResponse(**final)


# ---- HTTP handlers -----------------------------------------------------------


async def handle_roles() -> HubRolesResponse:
    return HubRolesResponse(hub_models=get_hub_models(), hub_instructions=HUB_ROLE_INSTRUCTIONS,
                            limits=HUB_LIMITS)


async def handle_plan(brief: HubRequest) -> PlanResponse:
    validate_overrides(brief)
    run = _Run(brief)
    await _run_planner(run)
    assert run.plan is not None
    plan_event = next(e for e in run.trace if e["event"] == "plan_ready")
    return PlanResponse(run_id=run.run_id, plan=run.plan, call=CallTrace(**plan_event["call"]))


async def handle_run(brief: HubRequest) -> HubResponse:
    validate_overrides(brief)
    return await run_hub(brief)


async def handle_export(request: ExportRequest) -> ExportResponse:
    try:
        path = write_workspace(request.run_id, [f.model_dump() for f in request.files],
                               request.manifest)
    except WorkspaceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ExportResponse(run_id=request.run_id, path=str(path), file_count=len(request.files))


async def handle_publish(request: PublishRequest) -> PublishResponse:
    try:
        info = await publish_workspace(request.run_id, request.repo_name, request.private,
                                       request.description)
    except WorkspaceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PublishResponse(run_id=request.run_id, repo_url=info["repo_url"], path=info["path"])
