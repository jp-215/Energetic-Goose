"""Generic chat-completion helper used by the evaluation pipeline.

Wraps the shared Canopy Wave client (any OpenAI-compatible endpoint) with
retries, latency accounting and a deterministic mock mode so the full
benchmark + persona-agent pipeline can run without inference credits.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .canopy import get_client
from .config import EVAL_CONFIG, is_mock_mode

Message = Dict[str, str]


@dataclass
class ChatResult:
    model: str
    text: str
    latency_ms: int
    retries_used: int
    status: str  # ok | error
    error: Optional[str] = None
    usage: Dict[str, int] = field(default_factory=dict)


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """First balanced JSON object in text (tolerates fences / preambles)."""
    decoder = json.JSONDecoder()
    idx = text.find("{")
    while idx != -1:
        try:
            payload, _ = decoder.raw_decode(text[idx:])
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        idx = text.find("{", idx + 1)
    return None


async def chat(
    model: str,
    messages: List[Message],
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    purpose: str = "generic",
) -> ChatResult:
    """One chat completion with retry/backoff. Never raises; errors are
    reported in the result so a single bad call cannot sink a session."""
    if is_mock_mode():
        return _mock_chat(model, messages, purpose)

    client = get_client()
    retries_used = 0
    last_error: Optional[str] = None
    for attempt in range(EVAL_CONFIG["max_retries"] + 1):
        started = time.perf_counter()
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens or EVAL_CONFIG["max_tokens"],
                timeout=EVAL_CONFIG["timeout_seconds"],
            )
            text = response.choices[0].message.content if response.choices else ""
            usage = {}
            if getattr(response, "usage", None):
                usage = {
                    "prompt_tokens": getattr(response.usage, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(response.usage, "completion_tokens", 0) or 0,
                }
            return ChatResult(
                model=model,
                text=(text or "").strip(),
                latency_ms=int((time.perf_counter() - started) * 1000),
                retries_used=retries_used,
                status="ok",
                usage=usage,
            )
        except Exception as exc:
            last_error = str(exc)
            if attempt < EVAL_CONFIG["max_retries"]:
                retries_used += 1
                await asyncio.sleep(EVAL_CONFIG["backoff_base_seconds"] ** retries_used)
    return ChatResult(
        model=model,
        text="",
        latency_ms=0,
        retries_used=retries_used,
        status="error",
        error=last_error or "Unknown error",
    )


# ---------------------------------------------------------------------------
# Mock mode
# ---------------------------------------------------------------------------

def _seed(*parts: str) -> int:
    digest = hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _mock_chat(model: str, messages: List[Message], purpose: str) -> ChatResult:
    """Deterministic fake responses keyed on (model, prompt) so mock sessions
    are reproducible yet differ between models."""
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    seed = _seed(model, last_user[:400])
    # Per-model "skill" so rankings in mock mode are not all identical.
    skill = 0.55 + (_seed(model) % 40) / 100.0  # 0.55 .. 0.94

    if purpose == "benchmark_mc":
        letters = re.findall(r"^\(?([A-J])[\).:]", last_user, flags=re.MULTILINE)
        gold = re.search(r"<<gold:([A-J])>>", system)
        if gold and (seed % 100) / 100.0 < skill:
            text = gold.group(1)
        else:
            text = letters[seed % len(letters)] if letters else "A"
        return ChatResult(model, text, 40 + seed % 300, 0, "ok")

    if purpose == "benchmark_numeric":
        gold = re.search(r"<<gold:([-0-9.]+)>>", system)
        if gold and (seed % 100) / 100.0 < skill:
            text = f"Working it through step by step... #### {gold.group(1)}"
        else:
            text = f"#### {(seed % 900) + 1}"
        return ChatResult(model, text, 40 + seed % 300, 0, "ok")

    if purpose == "agent_turn":
        openers = [
            "Thanks. One more thing I want to double check:",
            "Hmm, can you be more specific about",
            "Okay, that helps. But what about",
            "I'm not fully convinced. Can you explain",
        ]
        text = (
            f"{openers[seed % len(openers)]} the part of your answer that matters most for "
            f"my situation? Keep it short and concrete."
        )
        return ChatResult(model, text, 30 + seed % 100, 0, "ok")

    if purpose == "agent_feedback":
        # The simulator writes the feedback, but the score must track the model
        # under test, whose mock replies are tagged in the transcript.
        target = re.search(r"\[mock reply from ([^\]]+)\]", last_user)
        target_model = target.group(1) if target else model
        target_skill = 0.55 + (_seed(target_model) % 40) / 100.0
        base = 4 + target_skill * 5  # 6.75 .. 8.7
        def rating(dim: str) -> int:
            jitter = ((_seed(target_model, dim, last_user[:80]) % 30) - 15) / 10.0
            return max(1, min(10, round(base + jitter)))
        payload = {
            "ratings": {d: rating(d) for d in ["helpfulness", "accuracy", "clarity", "tone", "trust"]},
            "would_use_again": target_skill > 0.7,
            "summary": (
                f"[mock] Overall the assistant ({target_model}) handled my request reasonably well. "
                "It understood what I needed and stayed on topic."
            ),
            "highlights": ["Stayed on topic", "Answered quickly"],
            "complaints": ["Could have asked me a clarifying question earlier"],
            "quote": "It got most of the way there, but I had to push for specifics.",
        }
        return ChatResult(model, json.dumps(payload), 30 + seed % 100, 0, "ok")

    # target model replying to a persona
    text = (
        f"[mock reply from {model}] Here is a concrete, step-by-step answer to your request. "
        "First, clarify the goal. Second, apply the most direct approach. Third, verify the "
        "result and adjust. Let me know if you want me to go deeper on any step."
    )
    return ChatResult(model, text, 60 + seed % 400, 0, "ok")
