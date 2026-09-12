"""Workspace export + GitHub publish for The Firm runs.

Agent output is assembled in memory during a run; export writes it to
<repo root>/workspaces/<run_id>/ and publish turns that directory into a
GitHub repository via the authenticated `gh` CLI.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional

from .config import WORKSPACES_DIRNAME

SERVICE_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = SERVICE_DIR.parent.parent

RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,40}$")
MANIFEST_PATH = ".hub/run.json"


class WorkspaceError(RuntimeError):
    """Raised for invalid paths, missing tooling, or failed git/gh commands."""


def workspaces_root() -> Path:
    override = os.environ.get("HUB_WORKSPACES_DIR", "").strip()
    return Path(override).expanduser().resolve() if override else REPO_ROOT / WORKSPACES_DIRNAME


def safe_relative_path(raw: str) -> PurePosixPath:
    """Normalize an agent-supplied path; reject anything that escapes the workspace."""
    candidate = (raw or "").strip().replace("\\", "/")
    while candidate.startswith("./"):
        candidate = candidate[2:]
    if not candidate or candidate.startswith("/") or re.match(r"^[A-Za-z]:", candidate):
        raise WorkspaceError(f"unsafe file path: {raw!r}")
    parts = [p for p in candidate.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise WorkspaceError(f"unsafe file path: {raw!r}")
    if parts[0] == ".git":
        raise WorkspaceError(f"refusing to write inside .git: {raw!r}")
    return PurePosixPath(*parts)


def run_dir(run_id: str) -> Path:
    if not RUN_ID_RE.match(run_id or ""):
        raise WorkspaceError(f"invalid run id: {run_id!r}")
    return workspaces_root() / run_id


def write_workspace(run_id: str, files: Iterable[Dict[str, Any]],
                    manifest: Optional[Dict[str, Any]] = None) -> Path:
    """Materialize the workspace on disk (replacing any earlier export of the same run)."""
    target = run_dir(run_id)
    # Validate every path before touching the disk so a bad entry leaves nothing behind.
    planned = [(safe_relative_path(str(e.get("path", ""))), str(e.get("content", ""))) for e in files]

    root = workspaces_root()
    root.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)  # only ever our own export directory
    target.mkdir(parents=True)

    for rel, content in planned:
        dest = target / rel.as_posix()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

    if manifest is not None:
        manifest_file = target / MANIFEST_PATH
        manifest_file.parent.mkdir(parents=True, exist_ok=True)
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return target


async def _run(cmd: List[str], cwd: Path) -> str:
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        detail = (err or out).decode("utf-8", "replace").strip()
        raise WorkspaceError(f"{' '.join(cmd[:2])} failed: {detail}")
    return out.decode("utf-8", "replace").strip()


async def publish_workspace(run_id: str, repo_name: str, private: bool = True,
                            description: str = "") -> Dict[str, str]:
    """git init + commit the exported workspace, then create and push a GitHub repo."""
    target = run_dir(run_id)
    if not target.is_dir():
        raise WorkspaceError(f"run {run_id} has not been exported yet")
    gh = shutil.which("gh")
    git = shutil.which("git")
    if not gh or not git:
        raise WorkspaceError("GitHub publish needs the `git` and `gh` CLIs on PATH")

    if not (target / ".git").is_dir():
        await _run([git, "init", "-q", "-b", "main"], target)
    await _run([git, "add", "-A"], target)
    status = await _run([git, "status", "--porcelain"], target)
    if status:
        await _run(
            [git, "-c", "user.name=AI Court — The Firm", "-c", "user.email=hub@ai-court.local",
             "commit", "-q", "-m", f"The Firm run {run_id}"],
            target,
        )

    visibility = "--private" if private else "--public"
    cmd = [gh, "repo", "create", repo_name, visibility, "--source", str(target), "--push"]
    if description:
        cmd += ["--description", description]
    output = await _run(cmd, target)
    url_match = re.search(r"https://github\.com/\S+", output)
    if url_match:
        repo_url = url_match.group(0).rstrip("/")
    else:
        repo_url = await _run([gh, "repo", "view", "--json", "url", "-q", ".url"], target)
    return {"repo_url": repo_url, "path": str(target)}
