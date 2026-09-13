# Model Evaluation Arena

Evaluate cutting-edge models — Chinese and US — with a score that is **half open-source
benchmarks and half feedback from simulated users**, then explore every session as a Neo4j
graph. Runs on models hosted on **Canopy Wave** (OpenAI-compatible inference API).

```
model id(s)  ─►  ① benchmark session   (MMLU, GSM8K, ARC-Challenge, TruthfulQA, HellaSwag)  ─► benchmark score
             └►  ② agent session       (5 persona agents talk to the model, then grade it)   ─► agent score

final = 0.5 × benchmark score + 0.5 × agent score        (weights adjustable per run)
```

**Persona agents.** Each agent is a personality (background, traits, communication style, patience,
strictness, a scenario to accomplish, and priority weights over *helpfulness / accuracy / clarity /
tone / trust*). A simulator model plays the persona for a multi-turn conversation with the model
under test, then fills in a feedback form: 1–10 ratings per dimension, a summary, highlights,
complaints and a quotable line. The agent's score is the priority-weighted mean of its ratings.
Five personas ship by default (a startup founder, a physics professor, a bilingual Shanghai PM, a
staff engineer, and a 72-year-old retiree). Import your own on the **Agents** page (paste JSON or
upload a file — see `Demo/personas/extra_personas.json`), or via `POST /api/eval/personas/import`.

**Benchmarks.** Bundled sample subsets keep the app runnable offline; replace them with real rows
from Hugging Face (`.venv/bin/python scripts/fetch_benchmarks.py --rows 100`). Multiple-choice
benchmarks are graded by letter, GSM8K by final number. Items per benchmark is a per-run knob.

**Neo4j graph.** Every session is mirrored into a graph of how the agents used the model:

```
(Session)-[:EVALUATES]->(Model)          (Session)-[:RAN_BENCHMARK {score}]->(Benchmark)
(Agent)-[:PARTICIPATED_IN]->(Session)    (Agent)-[:INTERACTED_WITH {score,turns}]->(Model)
(Agent)-[:SENT]->(Turn)-[:NEXT]->(Turn)<-[:REPLIED]-(Model)
(Agent)-[:GAVE]->(Feedback)-[:ABOUT]->(Model)
```

Set `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` to write to a real Neo4j
(`docker compose -f docker-compose.neo4j.yml up -d`); otherwise an in-memory graph with the same
schema is used. The session page renders the graph (model at the centre, one spoke per agent, turns
along the spoke, feedback beyond) and shows the Cypher; with Neo4j the query box is live.

**Pages.** `/evaluate` — the arena: three setup cards (models with an access check, simulated
users as clickable avatars that open a personality sheet, benchmarks + weights), a run bar with the
call estimate, and live progress. `/sessions/<id>` — the output page: final score = benchmark +
agent halves, the users' avatars with their scores, the **Neo4j interaction graph** (always
visible), then tabs for feedback + transcripts, benchmark items, and tokens & timing. `/sessions`
(manage, re-run, delete), `/rankings` (our own leaderboard with CN vs US averages), `/agents`
(persona management + import). Design doc: `docs/SYSTEM_DESIGN.md`.

**Progress, ETA and tokens.** A run streams a `progress` event after every model call:
stage (`benchmark evaluation → simulated agents testing → scoring`), percent, elapsed time, an
ETA (measured per-call rates; flagged `~` while it is still extrapolated), and running token
spend split into benchmark calls, the model under test, and the simulator playing the personas.
Finished sessions carry a full token breakdown per benchmark, per agent and per conversation
round (**Tokens & timing** tab), plus wall-clock timings per stage.

**Which models can this key call?** `POST /api/eval/models/probe` (or the *check which models this
key can call* link on the Evaluate page) sends one tiny request per platform model and reports
which ids answer and which return 403. On the current demo key that is `minimax/minimax-m3` and
`moonshotai/kimi-k2.6`.

**Robustness on real keys.** 429s are retried with exponential back-off and jitter (up to five
times); at most four personas talk to the model at once; reasoning models get a 2 500-token budget
for the feedback form and a truncated form is salvaged by regex; a persona whose verdict still
cannot be parsed is marked `error`, excluded from the agent score and flagged on the output page.

**Demo without credits.** `CANOPYWAVE_API_KEY=mock` (or `EVAL_MOCK=1`) fakes every model call
deterministically, so the whole pipeline and UI can be exercised end to end.

## Also in this repo: the AI Court System

The original product on the same service: an AI court that deliberates cases. Three model roles:

| Role | Job | Default model |
|---|---|
| **Simple Counsel** | Fast, direct read of the case | `moonshotai/kimi-k2.6` |
| **Complex Counsel** | Deep analysis — precedent, counterarguments, edge cases | `minimax/minimax-m3` |
| **Judge** | Weighs both opinions, issues the final verdict | `minimax/minimax-m3` |

Flow: `case (context + query) → [simple ∥ complex] → judge → final verdict`

The UI has two tabs sharing the same node-editor surface:

| Tab | What it does |
|---|---|
| **Court** | The case flow above: intake → counsels → judge |
| **Coding Hub** | A multi-agent dev team: a **Planner** analyzes the brief, sizes the team, and assigns tasks; **Engineer** agents build concurrently and may **summon a helper** for a sub-task; an **Integrator** makes the workspace runnable. Every model call (prompt, model, latency, raw output) streams into a lifecycle panel, and the finished workspace can be exported to disk or published to GitHub. |

Hub flow: `brief → planner → [agent₁ ∥ agent₂ ∥ … (+ helpers)] → integrator → workspace`

> The original prototype cast (`kimi-k2.7-code-highspeed` / `kimi-k3` / `mimo-v2.5`) is listed by `/models` but returns **403** for the current demo key. Swap roles back via the `COURT_*_MODEL` env vars once your plan unlocks them. Hugging Face-hosted models (via the HF SDKs) are a planned expansion.

## Layout

```
notebooks/ai_court_prototype.ipynb   Research prototype (env setup → model calls → orchestration → demo docket)
services/court-orchestrator/         The backend service :8000 — middleware chain, court logic, Canopy Wave calls
  app/core/{benchmarks,agents,graph}.py   Model evaluation: benchmark runner, persona agents, Neo4j graph
  app/data/benchmarks/               Bundled benchmark sample subsets (MMLU, GSM8K, ARC, TruthfulQA, HellaSwag)
  app/data/personas/                 The five built-in persona agents
workspaces/<run_id>/                 Coding Hub exports (git-ignored); .hub/run.json carries the full trace
frontend/                            Vite + React + React Flow UI :5173 (evaluation pages, court canvas, coding hub)
scripts/dev.sh                       Starts the backend service (creates .venv on first run)
scripts/fetch_benchmarks.py          Pulls real benchmark rows from Hugging Face to replace the samples
docker-compose.neo4j.yml             Optional local Neo4j for the interaction graph
Demo/personas/extra_personas.json    Extra personalities to try the import feature
```

## Backend architecture

One dedicated service (one terminal, one process) assembled by the `create_app()` factory in `app/main.py` from two building blocks:

**Middleware chain** (`app/middleware/`), installed strictly in order — the app refuses to launch if the chain is broken:

1. `env_loader` — loads + validates every environment variable *before* the server launches (fail fast on missing/invalid)
2. `cors` — cross-origin access for the frontend (:5173)
3. `datacat` — console logger: prints an initialization banner on launch (service, models, masked key) and a log line per request
4. `preflight` — prerequisite guard verifying 1–3 actually installed before serving

**Layered routing** (request flow): Pydantic validation models (`app/models/`) → handlers holding the business logic (`app/handlers/`) → routers channeling requests (`app/routers/`) → registered on the app in `main.py` → frontend. Non-HTTP infrastructure (Canopy Wave client, config) lives in `app/core/`.

**Coding Hub endpoints** (`app/handlers/hub.py`, `app/routers/hub.py`):

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/hub/roles` | Hub models, role instructions, team caps |
| POST | `/api/hub/plan` | Planner only — preview the team without building |
| POST | `/api/hub/run` | Full run, one JSON response |
| POST | `/api/hub/run/stream` | Full run as NDJSON lifecycle events (what the UI uses) |
| POST | `/api/hub/export` | Write the workspace to `workspaces/<run_id>/` |
| POST | `/api/hub/publish` | Create + push a GitHub repo from the export via `gh` |

Caps live in `HUB_LIMITS` (`app/core/config.py`): at most 5 engineers per plan, 3 summoned helpers per run, helpers cannot summon helpers, 12 files per agent. Agent-written paths are sanitized (`app/core/workspace.py`) so nothing escapes the workspace.

> Scaling note: this branch intentionally compresses the earlier gateway + orchestrator split into one service. The two-service microservice layout is preserved on `infrastructure/backend-layer` for when it's time to scale back out.

## Setup

Credentials live in a `.env` (searched in `services/court-orchestrator/`, `services/`, repo root, then `Demo/`):

```
CANOPYWAVE_API_KEY=...
CANOPYWAVE_BASE_URL=https://inference.canopywave.io/v1
# optional Coding Hub role overrides
HUB_PLANNER_MODEL=minimax/minimax-m3
HUB_ENGINEER_MODEL=moonshotai/kimi-k2.6
HUB_INTEGRATOR_MODEL=minimax/minimax-m3
HUB_WORKSPACES_DIR=/somewhere/else   # defaults to <repo>/workspaces
```

Publishing from the Coding Hub needs the `gh` CLI logged in (`gh auth login`); the backend runs `git init` + `gh repo create --push` on the exported workspace.

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
- `POST /api/court/run` — run a case (see below)
- `GET /api/eval/meta` — model catalog (CN/US), platform models, benchmarks, weights, graph backend
- `POST /api/eval/models/probe` — which platform models this key can actually call
- `POST /api/eval/run` · `POST /api/eval/run/stream` — evaluate one or more models (NDJSON stream of
  `session_created`, `progress`, `benchmark_item`, `benchmark_result`, `agent_turn`, `agent_feedback`, `session_done`)
- `GET|DELETE /api/eval/sessions[/{id}]` · `POST /api/eval/sessions/{id}/rerun/stream`
- `GET /api/eval/sessions/{id}/graph` — nodes + relationships for the session (Neo4j or in-memory)
- `GET /api/eval/rankings` — leaderboard across completed sessions
- `GET /api/eval/graph/status` · `POST /api/eval/graph/cypher` (read-only, Neo4j only)
- `GET /api/eval/personas` · `POST /api/eval/personas/import` · `PUT|DELETE /api/eval/personas/{id}` · `POST /api/eval/personas/reset`
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
