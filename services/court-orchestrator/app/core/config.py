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


# ---------------------------------------------------------------------------
# Model evaluation (benchmarks + persona agents)
# ---------------------------------------------------------------------------

# Default 50/50 split between the open-source benchmark session and the
# persona-agent feedback session. Overridable per run.
EVAL_WEIGHTS = {"benchmark": 0.5, "agents": 0.5}

# Feedback dimensions every persona rates (1-10). Each persona carries its own
# priority weights over these dimensions.
FEEDBACK_DIMENSIONS = ["helpfulness", "accuracy", "clarity", "tone", "trust"]

EVAL_CONFIG = {
    "items_per_benchmark": 8,  # sample size per benchmark per run (cost control)
    "max_items_per_benchmark": 50,
    "agent_turns": 3,  # user turns per persona conversation
    "max_agent_turns": 6,
    "benchmark_concurrency": 4,
    "temperature": 0.0,
    "agent_temperature": 0.4,
    "max_tokens": 2000,  # benchmark answers + replies to personas (reasoning models need room)
    "timeout_seconds": 90,
    "max_retries": 2,
    "backoff_base_seconds": 1.5,
    # 429s from the platform: retry longer and harder than ordinary errors
    "rate_limit_retries": 5,
    "rate_limit_backoff_seconds": 4.0,
    # personas talking to the model at the same time (keeps the key under its rate limit)
    "agent_concurrency": 4,
    # reasoning models (minimax-m3 etc.) think before they answer; give the
    # feedback form and persona turns room so `content` is not cut off
    "simulator_turn_max_tokens": 1500,
    "feedback_max_tokens": 2500,
}

# Curated catalog of cutting-edge models for the evaluation dropdown, grouped
# by region. Any model id served by the inference platform can also be typed
# in directly; the catalog is only a convenience.
MODEL_CATALOG = [
    # Open-source models served by Canopy Wave (ids as listed by /v1/models)
    {
        "id": "moonshotai/kimi-k2.6",
        "vendor": "Moonshot AI",
        "region": "CN",
        "description": "Open-weight MoE flagship; strong agentic tool use and long-context reasoning.",
    },
    {
        "id": "moonshotai/kimi-k2.7-code",
        "vendor": "Moonshot AI",
        "region": "CN",
        "description": "K2.7 coding specialist; repo-scale code generation, debugging, agentic coding.",
    },
    {
        "id": "moonshotai/kimi-k2.7-code-highspeed",
        "vendor": "Moonshot AI",
        "region": "CN",
        "description": "Low-latency K2.7 code variant; tuned for fast, high-volume coding tasks.",
    },
    {
        "id": "moonshotai/kimi-k3",
        "vendor": "Moonshot AI",
        "region": "CN",
        "description": "Latest open-weight generation; frontier reasoning with native tool use.",
    },
    {
        "id": "minimax/minimax-m3",
        "vendor": "MiniMax",
        "region": "CN",
        "description": "Open-weight reasoning model; interleaved thinking, strong math and code.",
    },
    {
        "id": "xiaomimimo/mimo-v2.5",
        "vendor": "Xiaomi",
        "region": "CN",
        "description": "Compact open-weight model; efficient reasoning sized for edge deployments.",
    },
    {
        "id": "deepseek/deepseek-v4-flash",
        "vendor": "DeepSeek",
        "region": "CN",
        "description": "Lightweight V4 variant; fast general-purpose chat at low cost.",
    },
    {
        "id": "deepseek/deepseek-v4-pro",
        "vendor": "DeepSeek",
        "region": "CN",
        "description": "Flagship open-weight MoE; RL-trained deep reasoning for math, code, agents.",
    },
    {
        "id": "deepseek/deepseek-v4.1-flash",
        "vendor": "DeepSeek",
        "region": "CN",
        "description": "Latest efficiency line; better instruction following than v4-flash per token.",
    },
    {
        "id": "qwen/qwen3.8-flash-next",
        "vendor": "Alibaba Qwen",
        "region": "CN",
        "description": "Fast tier of the Qwen3.8 family; hybrid thinking modes, balanced quality/latency.",
    },
    {
        "id": "zai/glm-5.2",
        "vendor": "Zhipu AI",
        "region": "CN",
        "description": "Open-weight flagship; strong bilingual reasoning, coding, function calling.",
    },
    # US frontier models (need a platform / key that serves them)
    {
        "id": "openai/gpt-5",
        "vendor": "OpenAI",
        "region": "US",
        "description": "Frontier general model; balanced reasoning, instruction following, tool use.",
    },
    {
        "id": "openai/gpt-oss-120b",
        "vendor": "OpenAI",
        "region": "US",
        "description": "OpenAI open-weight 120B MoE; frontier-class quality on a single GPU node.",
    },
    {
        "id": "anthropic/claude-sonnet-5",
        "vendor": "Anthropic",
        "region": "US",
        "description": "Frontier reasoning with excellent coding and long-context handling.",
    },
    {
        "id": "anthropic/claude-opus-5",
        "vendor": "Anthropic",
        "region": "US",
        "description": "Top-tier reasoning depth for complex analysis and agentic work.",
    },
    {
        "id": "google/gemini-3-pro",
        "vendor": "Google",
        "region": "US",
        "description": "Frontier multimodal model; huge context, strong math and science reasoning.",
    },
    {
        "id": "meta-llama/llama-4-maverick",
        "vendor": "Meta",
        "region": "US",
        "description": "Open-weight MoE; natively multimodal with strong general and agent performance.",
    },
    {
        "id": "x-ai/grok-4",
        "vendor": "xAI",
        "region": "US",
        "description": "Frontier reasoning model with real-time knowledge orientation.",
    },
]

# Vendor prefix -> region, used to tag models that are not in the catalog.
VENDOR_REGIONS = {
    "moonshotai": "CN", "minimax": "CN", "xiaomimimo": "CN", "deepseek-ai": "CN",
    "deepseek": "CN", "qwen": "CN", "alibaba": "CN", "zai-org": "CN", "zai": "CN", "thudm": "CN",
    "baichuan": "CN", "01-ai": "CN", "internlm": "CN", "stepfun": "CN", "tencent": "CN",
    "openai": "US", "anthropic": "US", "google": "US", "meta-llama": "US", "meta": "US",
    "x-ai": "US", "xai": "US", "microsoft": "US", "nvidia": "US", "mistralai": "EU",
    "cohere": "US", "ai21": "IL",
}


def model_region(model_id: str) -> str:
    vendor = model_id.split("/", 1)[0].lower() if "/" in model_id else ""
    for entry in MODEL_CATALOG:
        if entry["id"] == model_id:
            return entry["region"]
    return VENDOR_REGIONS.get(vendor, "?")


def get_simulator_model() -> str:
    """Model that plays the persona agents (asks questions, writes feedback).
    Defaults to the court's judge model so it is always accessible on the key."""
    return os.environ.get("EVAL_SIMULATOR_MODEL", "").strip() or DEFAULT_ROLE_MODELS["judge"]


def is_mock_mode() -> bool:
    """Mock mode fakes every model call so the whole evaluation pipeline (and
    UI) can be exercised without spending inference credits."""
    flag = os.environ.get("EVAL_MOCK", "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    return os.environ.get("CANOPYWAVE_API_KEY", "").strip().lower() == "mock"


def get_neo4j_settings() -> Dict[str, str]:
    return {
        "uri": os.environ.get("NEO4J_URI", "").strip(),
        "user": os.environ.get("NEO4J_USER", "").strip() or "neo4j",
        "password": os.environ.get("NEO4J_PASSWORD", "").strip(),
        # empty = the server's default database (Aura instances are not always named "neo4j")
        "database": os.environ.get("NEO4J_DATABASE", "").strip(),
    }
