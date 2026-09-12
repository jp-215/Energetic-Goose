import asyncio
import json

import app.core.workspace as workspace
import app.handlers.hub as hub
import pytest
from app.core.canopy import ChatCallResult
from app.main import app
from app.models.hub import HubRequest, HubResponse
from fastapi.testclient import TestClient

PLAN_JSON = json.dumps({
    "analysis": "A tiny CLI app.",
    "team_size": 2,
    "rationale": "Core logic and tests split cleanly.",
    "agents": [
        {"id": "agent-1", "name": "Core", "role": "Backend Engineer", "specialty": "python",
         "tasks": [{"id": "t1", "title": "Implement", "description": "write app.py",
                    "deliverables": ["app.py"]}]},
        {"id": "agent-2", "name": "QA", "role": "Test Engineer", "specialty": "pytest",
         "tasks": [{"id": "t2", "title": "Tests", "description": "write tests",
                    "deliverables": ["test_app.py"]}]},
    ],
    "integration_notes": "python app.py",
})

AGENT_WITH_HELP = """=== SUMMARY ===
Wrote the core module.
=== FILE: app.py ===
print("hello")
=== END FILE ===
=== NOTES ===
Exposes main().
=== HELP ===
role: Docs Engineer
task: Write docs/USAGE.md describing the CLI flags.
reason: Out of scope for core.
"""

AGENT_PLAIN = """=== SUMMARY ===
Wrote tests.
=== FILE: test_app.py ===
```python
def test_ok():
    assert True
```
=== END FILE ===
=== NOTES ===
none
=== HELP ===
NONE
"""

HELPER_OUTPUT = """=== SUMMARY ===
Docs written.
=== FILE: docs/USAGE.md ===
# Usage
=== END FILE ===
=== HELP ===
role: Nobody
task: Should be ignored because helpers cannot summon.
reason: depth cap
"""

INTEGRATOR_OUTPUT = """=== SUMMARY ===
Added README.
=== FILE: README.md ===
# Demo
=== END FILE ===
=== FILE: ../../etc/passwd ===
nope
=== END FILE ===
=== RUN ===
python app.py
"""


def fake_call_factory(outputs_by_role, calls=None):
    async def fake_call(role, system_prompt, user_prompt, model_name, max_tokens,
                        timeout_seconds=None, temperature=None):
        if calls is not None:
            calls.append({"role": role, "prompt": user_prompt, "model": model_name})
        text = outputs_by_role(role, user_prompt)
        return ChatCallResult(
            role=role, model=model_name, system_prompt=system_prompt,
            user_prompt=user_prompt, text=text, latency_ms=3, retries_used=0, status="ok",
        )
    return fake_call


def default_outputs(role, prompt):
    if role == "planner":
        return PLAN_JSON
    if role == "integrator":
        return INTEGRATOR_OUTPUT
    if "summoned by" in prompt:
        return HELPER_OUTPUT
    if "You are Core" in prompt:
        return AGENT_WITH_HELP
    return AGENT_PLAIN


def brief(**overrides) -> HubRequest:
    payload = {"title": "Demo", "context": "ctx", "goal": "build it"}
    payload.update(overrides)
    return HubRequest(**payload)


def collect(brief_obj):
    async def run():
        return [e async for e in hub.run_hub_events(brief_obj)]
    return asyncio.run(run())


# ---- parsers -----------------------------------------------------------------


def test_parse_sectioned_output_strips_fences_and_reads_help():
    parsed = hub.parse_sectioned_output(AGENT_PLAIN)
    assert parsed["summary"] == "Wrote tests."
    assert parsed["files"][0]["path"] == "test_app.py"
    assert parsed["files"][0]["content"] == "def test_ok():\n    assert True\n"
    assert parsed["help"] is None

    parsed = hub.parse_sectioned_output(AGENT_WITH_HELP)
    assert parsed["help"] == {
        "role": "Docs Engineer",
        "task": "Write docs/USAGE.md describing the CLI flags.",
        "reason": "Out of scope for core.",
    }


def test_parse_sectioned_output_without_sections_keeps_text_as_summary():
    parsed = hub.parse_sectioned_output("just prose")
    assert parsed["summary"] == "just prose"
    assert parsed["files"] == []


def test_parse_plan_caps_team_and_dedupes_ids():
    raw = json.loads(PLAN_JSON)
    raw["agents"].append({"id": "agent-1", "name": "Dup", "role": "x", "tasks": []})
    plan, problem = hub.parse_plan(json.dumps(raw), max_agents=3)
    assert problem is None
    assert plan.team_size == 3
    assert len({a.id for a in plan.agents}) == 3

    plan, problem = hub.parse_plan(json.dumps(raw), max_agents=1)
    assert plan.team_size == 1


def test_parse_plan_rejects_garbage():
    plan, problem = hub.parse_plan("no json here", max_agents=3)
    assert plan is None and "JSON" in problem


# ---- orchestration -----------------------------------------------------------


def test_run_emits_full_lifecycle_and_summons_one_helper(monkeypatch):
    calls = []
    monkeypatch.setattr(hub, "call_chat", fake_call_factory(default_outputs, calls))
    events = collect(brief())
    names = [e["event"] for e in events]

    assert names[0] == "run_accepted"
    assert names[1] == "planner_started"
    assert names[2] == "plan_ready"
    assert names[3] == "team_assembled"
    assert names[-1] == "run_closed"
    assert names.count("agent_summoned") == 1
    # The helper's own help request is refused (depth cap), never a second summon.
    assert any(e["event"] == "summon_denied" and e["agent_id"] == "agent-1-helper" for e in events)
    assert names.count("agent_result") == 3

    summon = next(e for e in events if e["event"] == "agent_summoned")
    assert summon["parent_id"] == "agent-1"
    assert summon["agent"]["depth"] == 1
    assert summon["agent"]["role"] == "Docs Engineer"

    # Every call is auditable: prompt + raw output ride along with each result.
    result = next(e for e in events if e["event"] == "agent_result" and e["agent_id"] == "agent-1")
    assert result["result"]["call"]["user_prompt"]
    assert result["result"]["call"]["raw_output"] == AGENT_WITH_HELP
    assert result["result"]["helper_id"] == "agent-1-helper"

    closed = events[-1]["response"]
    response = HubResponse(**closed)
    assert response.status == "ok"
    assert [f.path for f in response.workspace] == ["README.md", "app.py", "docs/USAGE.md", "test_app.py"]
    assert response.integration.run_instructions == "python app.py"
    assert response.total_calls == 5  # planner + 2 engineers + helper + integrator
    # The integrator's path-traversal attempt is rejected and recorded.
    assert any(e["event"] == "file_rejected" and e["agent_id"] == "integrator" for e in events)
    # Teammates see each other's deliverables, not each other's prompts.
    core_prompt = next(c["prompt"] for c in calls if "You are Core" in c["prompt"])
    assert "test_app.py" in core_prompt


def test_helper_cap_is_enforced(monkeypatch):
    monkeypatch.setattr(hub, "call_chat", fake_call_factory(default_outputs))
    monkeypatch.setitem(hub.HUB_LIMITS, "max_helpers", 0)
    events = collect(brief())
    names = [e["event"] for e in events]
    assert "agent_summoned" not in names
    denied = next(e for e in events if e["event"] == "summon_denied")
    assert "cap" in denied["reason"]
    assert names.count("agent_result") == 2


def test_max_agents_request_limits_planner(monkeypatch):
    calls = []
    monkeypatch.setattr(hub, "call_chat", fake_call_factory(default_outputs, calls))
    events = collect(brief(max_agents=1))
    plan = next(e for e in events if e["event"] == "plan_ready")["plan"]
    assert plan["team_size"] == 1
    assert "Maximum team size: 1" in calls[0]["prompt"]


def test_unparseable_planner_falls_back_to_one_agent(monkeypatch):
    def outputs(role, prompt):
        return "I refuse to answer in JSON." if role == "planner" else default_outputs(role, prompt)

    monkeypatch.setattr(hub, "call_chat", fake_call_factory(outputs))
    events = collect(brief())
    plan = next(e for e in events if e["event"] == "plan_ready")["plan"]
    assert plan["fallback"] is True
    assert plan["team_size"] == 1
    assert events[-1]["event"] == "run_closed"


def test_model_call_failure_is_reported_not_raised(monkeypatch):
    async def failing(role, system_prompt, user_prompt, model_name, max_tokens,
                      timeout_seconds=None, temperature=None):
        return ChatCallResult(role=role, model=model_name, system_prompt=system_prompt,
                              user_prompt=user_prompt, text="", latency_ms=1, retries_used=3,
                              status="error", error="boom")

    monkeypatch.setattr(hub, "call_chat", failing)
    events = collect(brief())
    response = events[-1]["response"]
    assert events[-1]["event"] == "run_closed"
    assert response["status"] == "error"
    assert "agents failed: agent-1" in response["error"]
    assert "integrator: boom" in response["error"]
    assert response["total_retries"] >= 3


def test_conflicting_paths_are_traced(monkeypatch):
    def outputs(role, prompt):
        if role == "planner":
            return PLAN_JSON
        if role == "integrator":
            return INTEGRATOR_OUTPUT
        return "=== FILE: shared.py ===\nx = 1\n=== END FILE ===\n=== HELP ===\nNONE\n"

    monkeypatch.setattr(hub, "call_chat", fake_call_factory(outputs))
    events = collect(brief())
    conflict = next(e for e in events if e["event"] == "file_conflict")
    assert conflict["path"] == "shared.py"


# ---- workspace ---------------------------------------------------------------


def test_safe_relative_path_rejects_escapes():
    for bad in ("", "/etc/passwd", "../x", "src/../../x", "C:\\x", ".git/config"):
        with pytest.raises(workspace.WorkspaceError):
            workspace.safe_relative_path(bad)
    assert workspace.safe_relative_path("./src\\app.py").as_posix() == "src/app.py"


def test_write_workspace_materializes_files_and_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("HUB_WORKSPACES_DIR", str(tmp_path))
    files = [{"path": "app.py", "content": "print(1)\n"}, {"path": "docs/x.md", "content": "# x\n"}]
    target = workspace.write_workspace("run123456", files, {"run_id": "run123456"})
    assert target == tmp_path / "run123456"
    assert (target / "app.py").read_text() == "print(1)\n"
    assert (target / "docs" / "x.md").exists()
    assert json.loads((target / ".hub" / "run.json").read_text())["run_id"] == "run123456"
    # Re-export replaces stale files.
    workspace.write_workspace("run123456", [{"path": "only.txt", "content": "y"}])
    assert not (target / "app.py").exists()


def test_publish_runs_git_then_gh(tmp_path, monkeypatch):
    monkeypatch.setenv("HUB_WORKSPACES_DIR", str(tmp_path))
    workspace.write_workspace("run123456", [{"path": "a.txt", "content": "a"}])
    commands = []

    async def fake_run(cmd, cwd):
        commands.append(cmd)
        if cmd[1:3] == ["status", "--porcelain"]:
            return "?? a.txt"
        if cmd[1:3] == ["repo", "create"]:
            return "https://github.com/someone/demo-repo\n"
        return ""

    monkeypatch.setattr(workspace, "_run", fake_run)
    monkeypatch.setattr(workspace.shutil, "which", lambda name: f"/usr/bin/{name}")
    info = asyncio.run(workspace.publish_workspace("run123456", "demo-repo", private=True,
                                                   description="d"))
    assert info["repo_url"] == "https://github.com/someone/demo-repo"
    joined = [" ".join(c) for c in commands]
    assert any("init" in c for c in joined)
    assert any("commit" in c for c in joined)
    create = next(c for c in commands if c[1:3] == ["repo", "create"])
    assert "--private" in create and "--push" in create and "demo-repo" in create


def test_publish_requires_export_and_gh(tmp_path, monkeypatch):
    monkeypatch.setenv("HUB_WORKSPACES_DIR", str(tmp_path))
    with pytest.raises(workspace.WorkspaceError, match="not been exported"):
        asyncio.run(workspace.publish_workspace("missing00", "x"))
    workspace.write_workspace("run123456", [{"path": "a.txt", "content": "a"}])
    monkeypatch.setattr(workspace.shutil, "which", lambda name: None)
    with pytest.raises(workspace.WorkspaceError, match="gh"):
        asyncio.run(workspace.publish_workspace("run123456", "x"))


# ---- API ---------------------------------------------------------------------


def test_hub_roles_endpoint():
    response = TestClient(app).get("/api/hub/roles")
    assert response.status_code == 200
    body = response.json()
    assert set(body["hub_models"]) == {"planner", "engineer", "integrator"}
    assert body["limits"]["max_helpers"] >= 1


def test_hub_stream_endpoint(monkeypatch):
    monkeypatch.setattr(hub, "call_chat", fake_call_factory(default_outputs))
    client = TestClient(app)
    with client.stream("POST", "/api/hub/run/stream",
                       json={"title": "T", "context": "c", "goal": "g"}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-ndjson")
        events = [json.loads(line) for line in response.iter_lines() if line]
    assert events[0]["event"] == "run_accepted"
    assert events[-1]["event"] == "run_closed"
    HubResponse(**events[-1]["response"])


def test_hub_run_endpoint_and_plan_endpoint(monkeypatch):
    monkeypatch.setattr(hub, "call_chat", fake_call_factory(default_outputs))
    client = TestClient(app)
    response = client.post("/api/hub/run", json={"title": "T", "goal": "g"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    response = client.post("/api/hub/plan", json={"title": "T", "goal": "g", "max_agents": 2})
    assert response.status_code == 200
    assert response.json()["plan"]["team_size"] == 2
    assert response.json()["call"]["raw_output"] == PLAN_JSON


def test_hub_rejects_unknown_role_and_bad_export(tmp_path, monkeypatch):
    monkeypatch.setenv("HUB_WORKSPACES_DIR", str(tmp_path))
    client = TestClient(app)
    response = client.post("/api/hub/run", json={"title": "T", "model_overrides": {"judge": "x"}})
    assert response.status_code == 422
    response = client.post("/api/hub/export",
                           json={"run_id": "run123456", "files": [{"path": "../x", "content": ""}]})
    assert response.status_code == 422
    assert not (tmp_path / "run123456").exists()  # nothing written for a rejected export


def test_hub_export_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("HUB_WORKSPACES_DIR", str(tmp_path))
    client = TestClient(app)
    response = client.post("/api/hub/export", json={
        "run_id": "run123456",
        "files": [{"path": "a.txt", "content": "a", "author": "agent-1"}],
        "manifest": {"run_id": "run123456"},
    })
    assert response.status_code == 200
    assert response.json()["file_count"] == 1
    assert (tmp_path / "run123456" / "a.txt").exists()


def test_truncated_output_drops_only_the_unfinished_file(monkeypatch):
    truncated_agent = (
        "=== SUMMARY ===\nPartial.\n"
        "=== FILE: good.py ===\nx = 1\n=== END FILE ===\n"
        "=== FILE: cut.py ===\ndef f():\n    with open('x') as fh:\n"
    )

    async def fake_call(role, system_prompt, user_prompt, model_name, max_tokens,
                        timeout_seconds=None, temperature=None):
        text = PLAN_JSON if role == "planner" else INTEGRATOR_OUTPUT if role == "integrator" else truncated_agent
        return ChatCallResult(
            role=role, model=model_name, system_prompt=system_prompt, user_prompt=user_prompt,
            text=text, latency_ms=1, retries_used=0, status="ok",
            finish_reason="length" if role == "engineer" else "stop",
        )

    monkeypatch.setattr(hub, "call_chat", fake_call)
    events = collect(brief(max_agents=1))
    names = [e["event"] for e in events]
    assert "output_truncated" in names
    rejected = next(e for e in events if e["event"] == "file_rejected")
    assert rejected["path"] == "cut.py" and "max_tokens" in rejected["reason"]
    paths = [f["path"] for f in events[-1]["response"]["workspace"]]
    assert "good.py" in paths and "cut.py" not in paths
    result = next(e for e in events if e["event"] == "agent_result")
    assert result["result"]["call"]["finish_reason"] == "length"


def test_unterminated_last_file_is_kept_when_not_truncated():
    parsed = hub.parse_sectioned_output("=== FILE: a.py ===\nprint(1)\n")
    assert parsed["files"][0]["complete"] is False
    files, rejected = hub._files_from(parsed, "agent-1", 5, truncated=False)
    assert [f.path for f in files] == ["a.py"] and rejected == []
