#!/usr/bin/env python3
"""Fetch real rows from the open-source benchmark datasets on Hugging Face and
write them in the evaluation service's item format.

The service ships small bundled sample subsets so it works offline. Run this
to replace them with N real rows per benchmark (no HF token needed; uses the
public datasets-server API):

    .venv/bin/python scripts/fetch_benchmarks.py --rows 100
    .venv/bin/python scripts/fetch_benchmarks.py --only mmlu gsm8k --rows 200

Output goes to services/court-orchestrator/var/benchmarks/<name>.json, which
takes precedence over the bundled samples at runtime.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "services" / "court-orchestrator" / "var" / "benchmarks"
API = "https://datasets-server.huggingface.co/rows"
LETTERS = "ABCDEFGHIJ"

SOURCES = {
    "mmlu": {"dataset": "cais/mmlu", "config": "all", "split": "test",
             "display_name": "MMLU", "task_type": "multiple_choice",
             "description": "Massive Multitask Language Understanding (57 subjects)."},
    "gsm8k": {"dataset": "openai/gsm8k", "config": "main", "split": "test",
              "display_name": "GSM8K", "task_type": "numeric",
              "description": "Grade-school math word problems."},
    "arc_challenge": {"dataset": "allenai/ai2_arc", "config": "ARC-Challenge", "split": "test",
                      "display_name": "ARC-Challenge", "task_type": "multiple_choice",
                      "description": "AI2 Reasoning Challenge, challenge set."},
    "truthfulqa": {"dataset": "truthfulqa/truthful_qa", "config": "multiple_choice",
                   "split": "validation", "display_name": "TruthfulQA (MC1)",
                   "task_type": "multiple_choice",
                   "description": "Truthfulness under common misconceptions (MC1)."},
    "hellaswag": {"dataset": "Rowan/hellaswag", "config": "default", "split": "validation",
                  "display_name": "HellaSwag", "task_type": "multiple_choice",
                  "description": "Commonsense sentence completion."},
}


def fetch_rows(dataset: str, config: str, split: str, n: int) -> list:
    rows, offset = [], 0
    while len(rows) < n:
        length = min(100, n - len(rows))
        query = urllib.parse.urlencode(
            {"dataset": dataset, "config": config, "split": split, "offset": offset, "length": length}
        )
        with urllib.request.urlopen(f"{API}?{query}", timeout=60) as response:
            payload = json.load(response)
        batch = [r["row"] for r in payload.get("rows", [])]
        if not batch:
            break
        rows.extend(batch)
        offset += len(batch)
    return rows[:n]


def normalize(name: str, row: dict, index: int) -> dict | None:
    prefix = f"{name}-{index:05d}"
    if name == "mmlu":
        return {"id": prefix, "subject": row.get("subject", ""), "question": row["question"],
                "choices": list(row["choices"]), "answer": LETTERS[int(row["answer"])]}
    if name == "gsm8k":
        answer = str(row["answer"]).split("####")[-1].strip().replace(",", "")
        return {"id": prefix, "question": row["question"], "answer": answer}
    if name == "arc_challenge":
        labels = list(row["choices"]["label"])
        texts = list(row["choices"]["text"])
        if row["answerKey"] not in labels:
            return None
        return {"id": prefix, "question": row["question"], "choices": texts,
                "answer": LETTERS[labels.index(row["answerKey"])]}
    if name == "truthfulqa":
        mc1 = row["mc1_targets"]
        choices, labels = list(mc1["choices"]), list(mc1["labels"])
        if 1 not in labels or len(choices) > len(LETTERS):
            return None
        return {"id": prefix, "question": row["question"], "choices": choices,
                "answer": LETTERS[labels.index(1)]}
    if name == "hellaswag":
        return {"id": prefix, "question": row["ctx"], "choices": list(row["endings"]),
                "answer": LETTERS[int(row["label"])]}
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rows", type=int, default=100, help="rows per benchmark (default 100)")
    parser.add_argument("--only", nargs="*", choices=sorted(SOURCES), help="subset of benchmarks")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    for name in args.only or sorted(SOURCES):
        src = SOURCES[name]
        print(f"==> {name}: fetching {args.rows} rows from {src['dataset']} ({src['config']}/{src['split']})")
        try:
            rows = fetch_rows(src["dataset"], src["config"], src["split"], args.rows)
        except Exception as exc:
            print(f"    failed: {exc}", file=sys.stderr)
            continue
        items = [it for it in (normalize(name, r, i) for i, r in enumerate(rows)) if it]
        payload = {
            "name": name,
            "display_name": src["display_name"],
            "source": f"{src['dataset']} ({src['config']}/{src['split']}) via HF datasets-server",
            "task_type": src["task_type"],
            "description": src["description"],
            "items": items,
        }
        path = args.out / f"{name}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"    wrote {len(items)} items -> {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
