#!/usr/bin/env bash
# Runs the full local CI suite: lint, notebook validation, service tests, frontend build.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO_ROOT/.venv/bin/python"

if [ ! -x "$PY" ]; then
  echo "No .venv found — run ./scripts/dev.sh once first." >&2
  exit 1
fi

echo "==> ruff lint"
"$REPO_ROOT/.venv/bin/ruff" check "$REPO_ROOT/services" "$REPO_ROOT/scripts"

echo "==> notebook validation"
"$PY" "$REPO_ROOT/scripts/validate_notebook.py"

echo "==> court service tests"
(cd "$REPO_ROOT/services/court-orchestrator" && "$PY" -m pytest tests -q)

echo "==> frontend build"
(cd "$REPO_ROOT/frontend" && npm run build)

echo "All checks passed."
