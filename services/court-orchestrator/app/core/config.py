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
