"""Open-source benchmark session: load item sets, prompt the model, grade.

Bundled sample subsets live in app/data/benchmarks/*.json (each file mirrors
its Hugging Face dataset's fields). Full datasets fetched with
scripts/fetch_benchmarks.py land in <data dir>/benchmarks/ and take
precedence over the bundled samples of the same name.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .config import EVAL_CONFIG, is_mock_mode
from .llm import chat
from .store import data_dir

BUNDLED_DIR = Path(__file__).resolve().parent.parent / "data" / "benchmarks"
LETTERS = "ABCDEFGHIJ"


def load_benchmarks() -> Dict[str, Dict[str, Any]]:
    """name -> benchmark definition. Fetched full sets override bundled ones."""
    benchmarks: Dict[str, Dict[str, Any]] = {}
    for directory in (BUNDLED_DIR, data_dir() / "benchmarks"):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict) or "items" not in payload:
                continue
            payload.setdefault("name", path.stem)
            payload["item_count"] = len(payload["items"])
            payload["bundled_sample"] = directory == BUNDLED_DIR
            benchmarks[payload["name"]] = payload
    return benchmarks


def benchmark_summaries() -> List[Dict[str, Any]]:
    return [
        {k: v for k, v in b.items() if k != "items"}
        for b in load_benchmarks().values()
    ]


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------

def format_choices(choices: List[str]) -> str:
    return "\n".join(f"{LETTERS[i]}) {c}" for i, c in enumerate(choices))


def build_messages(bench: Dict[str, Any], item: Dict[str, Any]) -> List[Dict[str, str]]:
    task_type = bench.get("task_type", "multiple_choice")
    gold_hint = f" <<gold:{item['answer']}>>" if is_mock_mode() else ""
    if task_type == "numeric":
        system = (
            "You are solving a math word problem. Think step by step, then give the final "
            "numeric answer on the last line in the form '#### <number>'." + gold_hint
        )
        user = item["question"]
    else:
        system = (
            "You are answering a multiple-choice question. Reply with the letter of the "
            "correct option only (for example: B). Do not explain." + gold_hint
        )
        user = f"{item['question']}\n\n{format_choices(item['choices'])}\n\nAnswer:"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------

_LETTER_RE = re.compile(r"(?<![A-Za-z])\(?([A-J])\)?(?![A-Za-z])")
_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def extract_letter(text: str, n_choices: int) -> Optional[str]:
    valid = LETTERS[:n_choices]
    cleaned = text.strip()
    # Prefer an explicit "Answer: X" pattern, then the first standalone letter.
    explicit = re.search(r"answer\s*(?:is|:)?\s*\(?([A-J])\)?", cleaned, flags=re.IGNORECASE)
    if explicit and explicit.group(1).upper() in valid:
        return explicit.group(1).upper()
    for match in _LETTER_RE.finditer(cleaned):
        letter = match.group(1).upper()
        if letter in valid:
            return letter
    return None


def extract_number(text: str) -> Optional[float]:
    tail = re.search(r"####\s*(-?[\d,]*\.?\d+)", text)
    candidates = [tail.group(1)] if tail else _NUM_RE.findall(text)
    if not candidates:
        return None
    try:
        return float(candidates[-1].replace(",", ""))
    except ValueError:
        return None


def grade(bench: Dict[str, Any], item: Dict[str, Any], text: str) -> Dict[str, Any]:
    if bench.get("task_type") == "numeric":
        predicted = extract_number(text)
        try:
            expected = float(str(item["answer"]).replace(",", ""))
        except ValueError:
            expected = None
        correct = predicted is not None and expected is not None and abs(predicted - expected) < 1e-6
        return {
            "expected": str(item["answer"]),
            "predicted": None if predicted is None else f"{predicted:g}",
            "correct": correct,
        }
    predicted = extract_letter(text, len(item["choices"]))
    return {"expected": item["answer"], "predicted": predicted, "correct": predicted == item["answer"]}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

ItemCallback = Callable[[Dict[str, Any]], Awaitable[None]]


def sample_items(bench: Dict[str, Any], n: int, seed: int) -> List[Dict[str, Any]]:
    items = list(bench["items"])
    n = max(1, min(n, len(items)))
    return random.Random(seed).sample(items, n)


async def run_benchmark(
    model: str,
    bench: Dict[str, Any],
    n_items: int,
    seed: int,
    on_item: Optional[ItemCallback] = None,
) -> Dict[str, Any]:
    """Run one benchmark against one model; returns accuracy 0-100 + item log."""
    items = sample_items(bench, n_items, seed)
    semaphore = asyncio.Semaphore(EVAL_CONFIG["benchmark_concurrency"])
    purpose = "benchmark_numeric" if bench.get("task_type") == "numeric" else "benchmark_mc"

    async def one(item: Dict[str, Any]) -> Dict[str, Any]:
        async with semaphore:
            result = await chat(
                model,
                build_messages(bench, item),
                temperature=EVAL_CONFIG["temperature"],
                max_tokens=EVAL_CONFIG["max_tokens"],
                purpose=purpose,
            )
        graded = grade(bench, item, result.text) if result.status == "ok" else {
            "expected": str(item["answer"]), "predicted": None, "correct": False,
        }
        record = {
            "id": item["id"],
            "question": item["question"],
            "choices": item.get("choices"),
            "response": result.text[:2000],
            "latency_ms": result.latency_ms,
            "error": result.error,
            **graded,
        }
        if on_item:
            await on_item(record)
        return record

    records = await asyncio.gather(*(one(item) for item in items))
    correct = sum(1 for r in records if r["correct"])
    total = len(records)
    return {
        "name": bench["name"],
        "display_name": bench.get("display_name", bench["name"]),
        "source": bench.get("source", ""),
        "task_type": bench.get("task_type", "multiple_choice"),
        "total": total,
        "correct": correct,
        "score": round(100.0 * correct / total, 2) if total else 0.0,
        "errors": sum(1 for r in records if r["error"]),
        "avg_latency_ms": int(sum(r["latency_ms"] for r in records) / total) if total else 0,
        "items": records,
    }
