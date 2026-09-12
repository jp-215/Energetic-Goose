"""Middleware 1/4 — env loader.

Loads every environment variable the service knows about from the candidate
.env files into os.environ, then validates the required ones. Runs inside
create_app(), i.e. strictly before the server starts serving; a missing or
malformed variable aborts launch with a clear error.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI

SERVICE_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = SERVICE_DIR.parent.parent

ENV_CANDIDATES = [
    SERVICE_DIR / ".env",
    SERVICE_DIR.parent / ".env",  # services/.env — shared across services
    REPO_ROOT / ".env",
    REPO_ROOT / "Demo" / ".env",
]

REQUIRED_KEYS = ["CANOPYWAVE_API_KEY"]
KNOWN_KEYS = [
    "CANOPYWAVE_API_KEY",
    "CANOPYWAVE_BASE_URL",
    "COURT_SIMPLE_MODEL",
    "COURT_COMPLEX_MODEL",
    "COURT_JUDGE_MODEL",
    # Model evaluation (optional)
    "EVAL_SIMULATOR_MODEL",
    "EVAL_MOCK",
    "EVAL_DATA_DIR",
    # Neo4j graph of agent <-> model interactions (optional; falls back to an
    # in-memory graph persisted to disk when unset)
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "NEO4J_DATABASE",
]


def _normalize_secret(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value.strip().strip('"').strip("'")


def _manual_read_env_key(env_path: Path, key: str) -> Optional[str]:
    if not env_path.exists():
        return None
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        left, right = line.split("=", 1)
        if left.strip() == key:
            return _normalize_secret(right)
    return None


def load_env() -> dict:
    """Populate os.environ with every known key found in the candidate files,
    then validate. Returns a summary of where each key came from."""
    sources: dict = {}
    for key in KNOWN_KEYS:
        if _normalize_secret(os.environ.get(key)):
            sources[key] = "environment"
            continue
        for candidate in ENV_CANDIDATES:
            value = _manual_read_env_key(candidate, key)
            if value:
                os.environ[key] = value
                sources[key] = str(candidate)
                break

    missing = [key for key in REQUIRED_KEYS if not _normalize_secret(os.environ.get(key))]
    if missing:
        checked = ", ".join(str(path) for path in ENV_CANDIDATES)
        raise RuntimeError(
            f"env_loader: missing required environment variables {missing}. "
            f"Checked process env and: {checked}"
        )

    base_url = _normalize_secret(os.environ.get("CANOPYWAVE_BASE_URL"))
    if base_url and (not base_url.startswith("http") or "/v1" not in base_url):
        raise RuntimeError("env_loader: invalid CANOPYWAVE_BASE_URL, expected http(s)://.../v1")

    return sources


def install(app: FastAPI) -> None:
    sources = load_env()
    app.state.middleware_installed["env_loader"] = True
    app.state.env_sources = sources
