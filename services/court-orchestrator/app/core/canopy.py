"""Async Canopy Wave client: model calls, retries, structured parsing."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from .config import INFERENCE_CONFIG, get_api_key, get_base_url, get_role_models

_client: Optional[AsyncOpenAI] = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=get_api_key(), base_url=get_base_url())
    return _client


async def fetch_supported_model_ids() -> List[str]:
    client = get_client()
    model_page = await client.models.list()
    return sorted({m.id for m in model_page.data})


@dataclass
class ModelCallResult:
    role: str
    model: str
    answer: str
    verdict: str
    confidence: Optional[float]
    rationale: str
    latency_ms: int
    retries_used: int
    status: str
    error: Optional[str] = None


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Parse the first balanced JSON object found in text (handles markdown
    fences, reasoning preambles, and trailing commentary)."""
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


def parse_structured_response(text: str) -> Dict[str, Any]:
    verdict = "UNKNOWN"
    confidence = None
    rationale = ""
    cleaned = (text or "").strip()
    if not cleaned:
        return {"answer": "", "verdict": verdict, "confidence": confidence, "rationale": rationale}

    payload = _extract_json_object(cleaned)
    if payload is not None:
        verdict = str(payload.get("verdict", verdict)).upper()
        confidence_raw = payload.get("confidence")
        try:
            confidence = float(confidence_raw) if confidence_raw is not None else None
        except (TypeError, ValueError):
            confidence = None
        rationale = str(payload.get("rationale", ""))
        return {"answer": cleaned, "verdict": verdict, "confidence": confidence, "rationale": rationale}

    lowered = cleaned.lower()
    if "plaintiff" in lowered:
        verdict = "PLAINTIFF"
    elif "defendant" in lowered:
        verdict = "DEFENDANT"
    return {"answer": cleaned, "verdict": verdict, "confidence": confidence, "rationale": cleaned}


async def call_role_model(
    role: str,
    role_instruction: str,
    user_prompt: str,
    model_override: Optional[str] = None,
) -> ModelCallResult:
    client = get_client()
    model_name = model_override or get_role_models()[role]
    retries_used = 0
    last_error: Optional[str] = None
    system_prompt = (
        role_instruction
        + " Return strict JSON with keys: verdict, confidence, rationale. "
        + "verdict must be one of: PLAINTIFF, DEFENDANT, MIXED, UNKNOWN. "
        + "confidence must be a number between 0 and 1."
    )

    for attempt in range(INFERENCE_CONFIG["max_retries"] + 1):
        started = time.perf_counter()
        try:
            response = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=INFERENCE_CONFIG["temperature"],
                max_tokens=INFERENCE_CONFIG["max_tokens"],
                timeout=INFERENCE_CONFIG["timeout_seconds"],
            )
            raw_text = response.choices[0].message.content if response.choices else ""
            parsed = parse_structured_response(raw_text)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return ModelCallResult(
                role=role,
                model=model_name,
                answer=parsed["answer"],
                verdict=parsed["verdict"],
                confidence=parsed["confidence"],
                rationale=parsed["rationale"],
                latency_ms=elapsed_ms,
                retries_used=retries_used,
                status="ok",
            )
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            last_error = str(exc)
            if attempt < INFERENCE_CONFIG["max_retries"]:
                retries_used += 1
                backoff = INFERENCE_CONFIG["backoff_base_seconds"] ** retries_used
                await asyncio.sleep(backoff)
            else:
                return ModelCallResult(
                    role=role,
                    model=model_name,
                    answer="",
                    verdict="UNKNOWN",
                    confidence=None,
                    rationale="",
                    latency_ms=elapsed_ms,
                    retries_used=retries_used,
                    status="error",
                    error=last_error,
                )

    return ModelCallResult(
        role=role,
        model=model_name,
        answer="",
        verdict="UNKNOWN",
        confidence=None,
        rationale="",
        latency_ms=0,
        retries_used=retries_used,
        status="error",
        error=last_error or "Unknown error",
    )
