"""Service configuration.

Env-derived values are read lazily from os.environ, which the env_loader
middleware populates and validates before the server launches.
"""

from __future__ import annotations

import os
from typing import Dict

# Only models the current Canopy Wave key has inference access to.
# The original prototype roles (kimi-k2.7-code-highspeed / kimi-k3 / mimo-v2.5)
# return 403 on this account; restore them via COURT_*_MODEL once access is granted.
DEFAULT_ROLE_MODELS = {
    "simple": "moonshotai/kimi-k2.6",
    "complex": "minimax/minimax-m3",
    "judge": "minimax/minimax-m3",
}

ROLE_MODEL_ENV_KEYS = {
    "simple": "COURT_SIMPLE_MODEL",
    "complex": "COURT_COMPLEX_MODEL",
    "judge": "COURT_JUDGE_MODEL",
}

ROLE_INSTRUCTIONS = {
    "simple": (
        "You are Simple Counsel in an AI court. Argue the case plainly and quickly, "
        "focusing on the most obvious facts and the most direct reading of the dispute."
    ),
    "complex": (
        "You are Complex Counsel in an AI court. Analyze the case in depth: weigh "
        "precedent, counterarguments, edge cases, and second-order consequences before "
        "reaching a position."
    ),
    "judge": (
        "You are the Judge in an AI court. You are given the case plus the structured "
        "opinions of Simple Counsel and Complex Counsel. Weigh both, resolve their "
        "disagreements explicitly, and issue a final ruling."
    ),
}

INFERENCE_CONFIG = {
    "temperature": 0.2,
    "max_tokens": 2000,
    "timeout_seconds": 45,
    "max_retries": 3,
    "backoff_base_seconds": 1.5,
}

VALID_VERDICTS = {"PLAINTIFF", "DEFENDANT", "MIXED", "UNKNOWN"}

# ---- Coding Hub: multi-agent development team -------------------------------
# The hub is a separate tab from the court. A planner model analyzes the brief,
# decides the team, and assigns tasks; engineer agents build; any agent may
# summon a helper; an integrator assembles the runnable workspace.
DEFAULT_HUB_MODELS = {
    "planner": "minimax/minimax-m3",
    "engineer": "moonshotai/kimi-k2.6",
    "integrator": "minimax/minimax-m3",
}

HUB_MODEL_ENV_KEYS = {
    "planner": "HUB_PLANNER_MODEL",
    "engineer": "HUB_ENGINEER_MODEL",
    "integrator": "HUB_INTEGRATOR_MODEL",
}

HUB_ROLE_INSTRUCTIONS = {
    "planner": (
        "You are the Planner of an AI software development team. You receive a project "
        "brief and must analyze it, break it into concrete engineering tasks, decide how "
        "many agents the team needs, and assign every task to exactly one agent. Prefer "
        "the smallest team that can finish the work; never exceed the stated maximum."
    ),
    "engineer": (
        "You are an Engineer agent on an AI software development team. You own the tasks "
        "assigned to you and must produce complete, runnable source files. If part of "
        "your task needs a specialist you do not have time for, you may summon exactly "
        "one helper agent by describing the sub-task precisely."
    ),
    "integrator": (
        "You are the Integrator of an AI software development team. You receive every "
        "file the agents produced and must make the project runnable end to end: add or "
        "fix the README, entrypoint, dependency manifest, and any glue code that is "
        "missing. Do not rewrite files that already work."
    ),
}

# Hard caps that keep an agent team from growing without bound.
HUB_LIMITS = {
    "max_team_size": 5,   # planner may assign at most this many engineers
    "max_helpers": 3,     # total helpers that may be summoned in one run
    "max_depth": 1,       # helpers cannot summon helpers of their own
    "max_files_per_agent": 12,
}

HUB_INFERENCE_CONFIG = {
    "planner_max_tokens": 2500,
    "agent_max_tokens": 6000,
    "integrator_max_tokens": 8000,
    "timeout_seconds": 120,
}

WORKSPACES_DIRNAME = "workspaces"

CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# The inference platform currently serving the court. Hugging Face and
# Ollama (OpenClaw-hosted) integrations will register alongside this.
PLATFORM = {"id": "canopy-wave", "label": "Canopy Wave"}


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def get_api_key() -> str:
    api_key = os.environ.get("CANOPYWAVE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("CANOPYWAVE_API_KEY not loaded — did env_loader run?")
    return api_key


def get_base_url() -> str:
    base_url = os.environ.get("CANOPYWAVE_BASE_URL", "").strip() or "https://inference.canopywave.io/v1"
    return base_url.rstrip("/")


def get_role_models() -> Dict[str, str]:
    return {
        role: os.environ.get(env_key, "").strip() or DEFAULT_ROLE_MODELS[role]
        for role, env_key in ROLE_MODEL_ENV_KEYS.items()
    }


def get_hub_models() -> Dict[str, str]:
    return {
        role: os.environ.get(env_key, "").strip() or DEFAULT_HUB_MODELS[role]
        for role, env_key in HUB_MODEL_ENV_KEYS.items()
    }
