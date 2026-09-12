# AI Court System

An AI court that deliberates cases using models hosted on **Canopy Wave** (OpenAI-compatible inference API). Three model roles:

| Role | Job | Default model |
|---|---|---|
| **Simple Counsel** | Fast, direct read of the case | `moonshotai/kimi-k2.6` |
| **Complex Counsel** | Deep analysis — precedent, counterarguments, edge cases | `minimax/minimax-m3` |
| **Judge** | Weighs both opinions, issues the final verdict | `minimax/minimax-m3` |

Flow: `case (context + query) → [simple ∥ complex] → judge → final verdict`

> The original prototype cast (`kimi-k2.7-code-highspeed` / `kimi-k3` / `mimo-v2.5`) is listed by `/models` but returns **403** for the current demo key. Swap roles back via the `COURT_*_MODEL` env vars once your plan unlocks them. Hugging Face-hosted models (via the HF SDKs) are a planned expansion.

## Layout

```
notebooks/ai_court_prototype.ipynb   Research prototype (env setup → model calls → orchestration → demo docket)
services/court-orchestrator/         The backend service :8000 — middleware chain, court logic, Canopy Wave calls
frontend/                            Vite + React + React Flow node-editor UI :5173
scripts/dev.sh                       Starts the backend service (creates .venv on first run)
```

## Backend architecture

One dedicated service (one terminal, one process) assembled by the `create_app()` factory in `app/main.py` from two building blocks:

**Middleware chain** (`app/middleware/`), installed strictly in order — the app refuses to launch if the chain is broken:

1. `env_loader` — loads + validates every environment variable *before* the server launches (fail fast on missing/invalid)
2. `cors` — cross-origin access for the frontend (:5173)
3. `datacat` — console logger: prints an initialization banner on launch (service, models, masked key) and a log line per request
4. `preflight` — prerequisite guard verifying 1–3 actually installed before serving

**Layered routing** (request flow): Pydantic validation models (`app/models/`) → handlers holding the business logic (`app/handlers/`) → routers channeling requests (`app/routers/`) → registered on the app in `main.py` → frontend. Non-HTTP infrastructure (Canopy Wave client, config) lives in `app/core/`.

> Scaling note: this branch intentionally compresses the earlier gateway + orchestrator split into one service. The two-service microservice layout is preserved on `infrastructure/backend-layer` for when it's time to scale back out.

## Setup

Credentials live in a `.env` (searched in `services/*/`, repo root, then `Demo/`):

```
CANOPYWAVE_API_KEY=...
CANOPYWAVE_BASE_URL=https://inference.canopywave.io/v1
```

### Backend (one terminal)

```bash
./scripts/dev.sh          # court service on :8000
```

Or manually:

```bash
python3 -m venv .venv
.venv/bin/pip install -r services/court-orchestrator/requirements.txt
cd services/court-orchestrator/app && python main.py     # or: uvicorn app.main:app --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev               # http://localhost:5173 (proxies /api -> :8000)
```

### Notebook

```bash
.venv/bin/pip install openai python-dotenv pandas jupyter
jupyter lab notebooks/ai_court_prototype.ipynb
```

## CI & testing

GitHub Actions (`.github/workflows/ci.yml`) runs three jobs on every push/PR: notebook validation, service lint + tests, and the frontend typecheck + build. No Canopy Wave key is needed in CI — all model calls are mocked.

Run the identical suite locally:

```bash
.venv/bin/pip install -r requirements-dev.txt
./scripts/test.sh        # ruff lint → notebook check → pytest → frontend build
```

## API

- `GET /api/health` — service health
- `GET /api/models` — model ids available on Canopy Wave
- `GET /api/roles` — role → model map, role instructions, inference config
- `POST /api/court/run` — run a case:

```bash
curl -X POST http://localhost:8000/api/court/run -H 'Content-Type: application/json' -d '{
  "title": "Orchard Lane Fence Dispute",
  "context": "…the facts…",
  "query": "Is the defendant entitled to the remaining balance?",
  "model_overrides": {"judge": "minimax/minimax-m3"}
}'
```

Response includes per-role results (`verdict`, `confidence`, `rationale`, `latency_ms`, `retries_used`) plus the judge's `final_verdict` and `judge_rationale`.
