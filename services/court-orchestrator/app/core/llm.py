"""Generic chat-completion helper used by the evaluation pipeline.

Wraps the shared Canopy Wave client (any OpenAI-compatible endpoint) with
retries, latency accounting and a deterministic mock mode so the full
benchmark + persona-agent pipeline can run without inference credits.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
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
    # {"prompt": n, "completion": n, "total": n, "estimated": bool}
    usage: Dict[str, Any] = field(default_factory=dict)


def estimate_tokens(text: str) -> int:
    """Rough fallback when the provider returns no usage (~4 chars/token)."""
    return max(1, len(text or "") // 4)


def make_usage(prompt: Optional[int], completion: Optional[int],
               messages: List[Message], text: str) -> Dict[str, Any]:
    if prompt is None or completion is None:
        prompt = estimate_tokens("".join(m["content"] for m in messages))
        completion = estimate_tokens(text)
        return {"prompt": prompt, "completion": completion, "total": prompt + completion,
                "estimated": True}
    return {"prompt": int(prompt), "completion": int(completion),
            "total": int(prompt) + int(completion), "estimated": False}


def add_usage(total: Dict[str, Any], usage: Dict[str, Any]) -> Dict[str, Any]:
    """Accumulate usage dicts (in place) and return the total."""
    for key in ("prompt", "completion", "total"):
        total[key] = int(total.get(key, 0)) + int(usage.get(key, 0) or 0)
    total["estimated"] = bool(total.get("estimated", False) or usage.get("estimated", False))
    return total


def empty_usage() -> Dict[str, Any]:
    return {"prompt": 0, "completion": 0, "total": 0, "estimated": False}


def _is_rate_limit(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    return status == 429 or "429" in str(exc) or "rate limit" in str(exc).lower()


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
    for attempt in range(EVAL_CONFIG["rate_limit_retries"] + 1):
        started = time.perf_counter()
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens or EVAL_CONFIG["max_tokens"],
                timeout=EVAL_CONFIG["timeout_seconds"],
            )
            message = response.choices[0].message if response.choices else None
            text = (getattr(message, "content", None) if message else None) or ""
            if not text.strip() and message is not None:
                # Reasoning models can spend the whole budget thinking and return
                # an empty `content`; surface the reasoning so a parser can try it.
                text = getattr(message, "reasoning_content", None) or getattr(message, "reasoning", None) or ""
            raw_usage = getattr(response, "usage", None)
            usage = make_usage(
                getattr(raw_usage, "prompt_tokens", None) if raw_usage else None,
                getattr(raw_usage, "completion_tokens", None) if raw_usage else None,
                messages, text,
            )
            return ChatResult(
                model=model,
                text=text.strip(),
                latency_ms=int((time.perf_counter() - started) * 1000),
                retries_used=retries_used,
                status="ok",
                usage=usage,
            )
        except Exception as exc:
            last_error = str(exc)
            rate_limited = _is_rate_limit(exc)
            max_retries = EVAL_CONFIG["rate_limit_retries"] if rate_limited else EVAL_CONFIG["max_retries"]
            if attempt < max_retries:
                retries_used += 1
                if rate_limited:  # 429: back off hard, with jitter so parallel personas de-sync
                    delay = min(60.0, EVAL_CONFIG["rate_limit_backoff_seconds"] * (2 ** (retries_used - 1)))
                    delay *= 0.75 + 0.5 * random.random()
                else:
                    delay = EVAL_CONFIG["backoff_base_seconds"] ** retries_used
                await asyncio.sleep(delay)
            else:
                break
    return ChatResult(
        model=model,
        text="",
        latency_ms=0,
        retries_used=retries_used,
        status="error",
        error=last_error or "Unknown error",
        usage=empty_usage(),
    )


# ---------------------------------------------------------------------------
# Mock mode
# ---------------------------------------------------------------------------

def _seed(*parts: str) -> int:
    digest = hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _mock_chat(model: str, messages: List[Message], purpose: str) -> ChatResult:
    result = _mock_chat_inner(model, messages, purpose)
    result.usage = make_usage(None, None, messages, result.text)
    return result


def _mock_chat_inner(model: str, messages: List[Message], purpose: str) -> ChatResult:
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
