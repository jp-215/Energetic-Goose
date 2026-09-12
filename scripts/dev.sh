#!/usr/bin/env bash
# Starts the AI Court service (one terminal, one process) on :8000.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$REPO_ROOT/.venv"

if [ ! -d "$VENV" ]; then
  echo "Creating venv at $VENV ..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip
  "$VENV/bin/pip" install -r "$REPO_ROOT/services/court-orchestrator/requirements.txt"
fi

cd "$REPO_ROOT/services/court-orchestrator"
exec "$VENV/bin/uvicorn" app.main:app --port 8000 --reload
