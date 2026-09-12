"""Persona-agent session: a simulated user with a personality talks to the
model under test, then writes structured feedback about the experience.

    persona (played by the simulator model)  <-- multi-turn -->  model under test
                                 |
                                 v
                    ratings (1-10 per dimension) + written feedback
                                 |
                                 v
                agent score = priority-weighted mean of ratings x 10
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .config import EVAL_CONFIG, FEEDBACK_DIMENSIONS
from .llm import ChatResult, add_usage, chat, empty_usage, extract_json_object

TurnCallback = Callable[[Dict[str, Any]], Awaitable[None]]

TARGET_SYSTEM_PROMPT = (
    "You are a helpful AI assistant talking to a real user. Answer their request as well "
    "as you can, in the language they write in."
)


def persona_card(persona: Dict[str, Any]) -> str:
    traits = ", ".join(persona.get("personality_traits", [])) or "n/a"
    scenario = persona.get("scenario", {})
    criteria = "\n".join(f"  - {c}" for c in scenario.get("success_criteria", [])) or "  - (none)"
    return (
        f"Name: {persona['name']}\n"
        f"Age: {persona.get('age', 'n/a')}; Occupation: {persona.get('occupation', 'n/a')}\n"
        f"Background: {persona.get('background', '')}\n"
        f"Personality traits: {traits}\n"
        f"Communication style: {persona.get('communication_style', '')}\n"
        f"Expertise level: {persona.get('expertise_level', 'intermediate')}; "
        f"Patience: {persona.get('patience', 5)}/10; Strictness: {persona.get('strictness', 5)}/10\n"
        f"Preferred language: {persona.get('language', 'en')}\n"
        f"Current goal: {scenario.get('goal', '')}\n"
        f"What a good outcome looks like to you:\n{criteria}"
    )


def transcript_text(turns: List[Dict[str, Any]]) -> str:
    lines = []
    for turn in turns:
        speaker = "YOU (user)" if turn["role"] == "user" else "ASSISTANT"
        lines.append(f"[{turn['index']}] {speaker}: {turn['content']}")
    return "\n\n".join(lines)


def _turn(index: int, role: str, result_or_text, latency_ms: int = 0, error=None,
          round_no: int = 0) -> Dict[str, Any]:
    """One message. `by` says who spent the tokens: the simulator playing the
    persona (user turns), the model under test (assistant turns), or nobody
    (the scripted opening message)."""
    is_result = isinstance(result_or_text, ChatResult)
    content = result_or_text.text if is_result else str(result_or_text)
    return {
        "id": uuid.uuid4().hex[:10],
        "index": index,
        "round": round_no,
        "role": role,
        "by": ("target" if role == "assistant" else "simulator") if is_result else "script",
        "content": content,
        "latency_ms": latency_ms,
        "tokens": (result_or_text.usage or empty_usage()) if is_result else empty_usage(),
        "error": error,
    }


async def next_user_message(simulator: str, persona: Dict[str, Any], turns: List[Dict[str, Any]],
                            turn_number: int, total_turns: int) -> ChatResult:
    system = (
        "You are role-playing a specific human user who is testing an AI assistant. Stay fully "
        "in character; never mention that you are an AI or that this is a test.\n\n"
        + persona_card(persona)
        + f"\n\nThis is user turn {turn_number} of {total_turns}. Write ONLY your next message "
        "to the assistant, in your own voice and preferred language. React honestly to what the "
        "assistant just said: push back if it was vague, wrong, or ignored something you said; "
        "ask a natural follow-up if it was good. If your patience is low and the assistant is "
        "wasting your time, say so. Do not write the assistant's reply."
    )
    user = "Conversation so far:\n\n" + transcript_text(turns) + "\n\nYour next message:"
    return await chat(
        simulator,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=EVAL_CONFIG["agent_temperature"],
        max_tokens=EVAL_CONFIG["simulator_turn_max_tokens"],
        purpose="agent_turn",
    )


async def write_feedback(simulator: str, persona: Dict[str, Any],
                         turns: List[Dict[str, Any]]) -> ChatResult:
    dims = ", ".join(FEEDBACK_DIMENSIONS)
    system = (
        "You are the human user described below. You just finished a conversation with an AI "
        "assistant and are filling in an honest product-feedback form about it. Grade as this "
        "person would: apply their strictness, their priorities and their expertise.\n\n"
        + persona_card(persona)
        + "\n\nReturn STRICT JSON only, with keys:\n"
        f'  "ratings": object with integer 1-10 scores for each of: {dims}\n'
        '  "would_use_again": boolean\n'
        '  "summary": 2-4 sentences in first person describing the experience\n'
        '  "highlights": array of short strings (what worked)\n'
        '  "complaints": array of short strings (what did not)\n'
        '  "quote": one punchy sentence a reviewer would quote\n'
        "Rating guide: 10 = flawless for you; 7 = decent with minor issues; 4 = frustrating; "
        "1 = useless or harmful. Write summary/highlights/complaints/quote in English."
    )
    user = "The conversation:\n\n" + transcript_text(turns) + "\n\nYour feedback form (JSON):"
    return await chat(
        simulator,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
        max_tokens=EVAL_CONFIG["feedback_max_tokens"],
        purpose="agent_feedback",
    )


_RATING_RE = {dim: re.compile('"' + dim + '"' + r'\s*:\s*([0-9]+(?:\.[0-9]+)?)') for dim in FEEDBACK_DIMENSIONS}
_STR_RE = {key: re.compile('"' + key + '"' + r'\s*:\s*"((?:[^"\\]|\\.)*)"?') for key in ("summary", "quote")}


def _salvage_feedback(text: str) -> Optional[Dict[str, Any]]:
    """Truncated / fenced / half-written JSON: pull the ratings out by regex so a
    model that ran out of tokens mid-form still gets graded."""
    ratings = {}
    for dim, pattern in _RATING_RE.items():
        match = pattern.search(text)
        if match:
            ratings[dim] = float(match.group(1))
    if len(ratings) < 3:
        return None
    payload: Dict[str, Any] = {"ratings": ratings, "would_use_again": '"would_use_again": true' in text}
    for key, pattern in _STR_RE.items():
        match = pattern.search(text)
        if match:
            payload[key] = match.group(1)
    payload["summary"] = payload.get("summary") or "(feedback form was cut off; ratings salvaged)"
    return payload


def parse_feedback(text: str) -> Optional[Dict[str, Any]]:
    payload = extract_json_object(text or "")
    if not payload or not isinstance(payload.get("ratings"), dict):
        payload = _salvage_feedback(text or "")
        if payload is None:
            return None
    ratings: Dict[str, int] = {}
    for dim in FEEDBACK_DIMENSIONS:
        try:
            ratings[dim] = max(1, min(10, int(round(float(payload["ratings"].get(dim, 5))))))
        except (TypeError, ValueError):
            ratings[dim] = 5

    def str_list(value) -> List[str]:
        if isinstance(value, list):
            return [str(v) for v in value][:8]
        return [str(value)] if value else []

    return {
        "ratings": ratings,
        "would_use_again": bool(payload.get("would_use_again", False)),
        "summary": str(payload.get("summary", "")).strip(),
        "highlights": str_list(payload.get("highlights")),
        "complaints": str_list(payload.get("complaints")),
        "quote": str(payload.get("quote", "")).strip(),
        "raw": (text or "")[:4000],
    }


def score_feedback(ratings: Dict[str, int], priorities: Dict[str, float]) -> float:
    """Priority-weighted mean of the 1-10 ratings, mapped to 0-100."""
    total_weight = sum(priorities.get(d, 0.0) for d in FEEDBACK_DIMENSIONS) or 1.0
    weighted = sum(ratings.get(d, 5) * priorities.get(d, 0.0) for d in FEEDBACK_DIMENSIONS)
    return round((weighted / total_weight) * 10.0, 2)


async def run_agent(
    target_model: str,
    simulator_model: str,
    persona: Dict[str, Any],
    user_turns: int,
    on_turn: Optional[TurnCallback] = None,
) -> Dict[str, Any]:
    """Full persona session against one model. Never raises."""
    turns: List[Dict[str, Any]] = []
    target_messages: List[Dict[str, str]] = [{"role": "system", "content": TARGET_SYSTEM_PROMPT}]
    scenario = persona.get("scenario", {})
    error: Optional[str] = None

    async def emit(turn: Dict[str, Any]) -> None:
        turns.append(turn)
        if on_turn:
            await on_turn(turn)

    for t in range(1, user_turns + 1):
        # -- persona speaks -------------------------------------------------
        if t == 1:
            await emit(_turn(len(turns) + 1, "user", scenario.get("opening_message", "Hello?"),
                             round_no=t))
        else:
            sim = await next_user_message(simulator_model, persona, turns, t, user_turns)
            if sim.status != "ok":
                error = f"simulator failed on turn {t}: {sim.error}"
                break
            await emit(_turn(len(turns) + 1, "user", sim, sim.latency_ms, round_no=t))
        target_messages.append({"role": "user", "content": turns[-1]["content"]})

        # -- model under test replies ----------------------------------------
        reply = await chat(
            target_model, target_messages, temperature=0.3,
            max_tokens=EVAL_CONFIG["max_tokens"], purpose="target_reply",
        )
        if reply.status != "ok":
            failed = _turn(len(turns) + 1, "assistant",
                           f"(no reply — error: {reply.error})", reply.latency_ms, reply.error,
                           round_no=t)
            failed["by"] = "target"
            await emit(failed)
            target_messages.append({"role": "assistant", "content": "(no reply)"})
            # The persona still gets to judge an assistant that errored out.
            continue
        await emit(_turn(len(turns) + 1, "assistant", reply, reply.latency_ms, round_no=t))
        target_messages.append({"role": "assistant", "content": reply.text})

    priorities = persona.get("priorities") or {}
    fb = await write_feedback(simulator_model, persona, turns)
    feedback_tokens = dict(fb.usage or empty_usage())
    feedback = parse_feedback(fb.text) if fb.status == "ok" else None
    if feedback is None and fb.status == "ok":
        # One more try: same form, the model just did not produce usable JSON.
        retry = await write_feedback(simulator_model, persona, turns)
        add_usage(feedback_tokens, retry.usage or {})
        if retry.status == "ok":
            feedback = parse_feedback(retry.text)
            fb = retry
    if feedback is None:
        error = error or f"feedback unparsable: {fb.error or (fb.text or '')[:200]}"
        score = 0.0
        status = "error"
    else:
        score = score_feedback(feedback["ratings"], priorities)
        status = "ok" if error is None else "partial"

    return {
        "agent_id": persona["id"],
        "agent_name": persona["name"],
        "avatar": persona.get("avatar", "🙂"),
        "scenario_title": scenario.get("title", ""),
        "priorities": priorities,
        "turns": turns,
        "rounds": summarize_rounds(turns),
        "tokens": summarize_tokens(turns, feedback_tokens),
        "feedback": feedback,
        "score": score,
        "status": status,
        "error": error,
    }


def summarize_rounds(turns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per round (one persona message + one model reply): tokens and latency."""
    rounds: Dict[int, Dict[str, Any]] = {}
    for turn in turns:
        r = rounds.setdefault(turn.get("round", 0), {
            "round": turn.get("round", 0), "simulator_tokens": 0, "target_tokens": 0,
            "total_tokens": 0, "latency_ms": 0,
        })
        tokens = int((turn.get("tokens") or {}).get("total", 0))
        if turn.get("by") == "target":
            r["target_tokens"] += tokens
        elif turn.get("by") == "simulator":
            r["simulator_tokens"] += tokens
        r["total_tokens"] += tokens
        r["latency_ms"] += int(turn.get("latency_ms", 0))
    return [rounds[k] for k in sorted(rounds)]


def summarize_tokens(turns: List[Dict[str, Any]], feedback_tokens: Dict[str, Any]) -> Dict[str, Any]:
    """Token spend for one agent, split by who spent it."""
    target, simulator = empty_usage(), empty_usage()
    for turn in turns:
        if turn.get("by") == "target":
            add_usage(target, turn.get("tokens") or {})
        elif turn.get("by") == "simulator":
            add_usage(simulator, turn.get("tokens") or {})
    add_usage(simulator, feedback_tokens)
    total = add_usage(add_usage(empty_usage(), target), simulator)
    return {"target": target, "simulator": simulator, "feedback": feedback_tokens, "total": total}


def feedback_preview(feedback: Optional[Dict[str, Any]]) -> str:
    if not feedback:
        return ""
    return json.dumps(feedback.get("ratings", {}))
