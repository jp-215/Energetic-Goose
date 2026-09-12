#!/usr/bin/env python3
"""CI check: every notebook is valid nbformat JSON and every code cell compiles."""

from __future__ import annotations

import sys
from pathlib import Path

import nbformat

REPO_ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK_DIR = REPO_ROOT / "notebooks"


def check(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        nb = nbformat.read(str(path), as_version=4)
        nbformat.validate(nb)
    except Exception as exc:
        return [f"{path.name}: invalid notebook: {exc}"]
    for i, cell in enumerate(nb.cells):
        if cell.cell_type != "code":
            continue
        source = cell.source
        # %-magics are jupyter-only; blank them out for the compile check.
        cleaned = "\n".join(
            "" if line.lstrip().startswith(("%", "!")) else line
            for line in source.splitlines()
        )
        try:
            compile(cleaned, f"{path.name}[cell {i}]", "exec")
        except SyntaxError as exc:
            errors.append(f"{path.name}[cell {i}]: {exc}")
    return errors


def main() -> int:
    notebooks = sorted(NOTEBOOK_DIR.glob("*.ipynb"))
    if not notebooks:
        print(f"No notebooks found under {NOTEBOOK_DIR}", file=sys.stderr)
        return 1
    failures: list[str] = []
    for nb_path in notebooks:
        errors = check(nb_path)
        status = "FAIL" if errors else "OK"
        print(f"[{status}] {nb_path.relative_to(REPO_ROOT)}")
        failures.extend(errors)
    for err in failures:
        print(f"  {err}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
