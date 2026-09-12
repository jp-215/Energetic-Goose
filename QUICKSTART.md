# Quick start — Model Evaluation

Evaluate cutting-edge models (Chinese and US) with a score that is **50% open-source
benchmarks + 50% feedback from persona agents** that actually use the model, and map how
the agents used it in a Neo4j graph.

## 1. Prerequisites

- Python 3.12+ and Node 18+
- A Canopy Wave key (`CANOPYWAVE_API_KEY`) for real model calls — **or** use mock mode (no key needed, see below)
- Optional: Docker, if you want a real Neo4j instead of the built-in in-memory graph

## 2. Configure

```bash
cp services/court-orchestrator/.env.example services/court-orchestrator/.env
```

Edit `services/court-orchestrator/.env`:

```
CANOPYWAVE_API_KEY=your-key-here          # or: mock   (fakes every model call, zero credits)
CANOPYWAVE_BASE_URL=https://inference.canopywave.io/v1

# optional
# EVAL_SIMULATOR_MODEL=minimax/minimax-m3   # model that plays the persona agents
# NEO4J_URI=bolt://localhost:7687           # leave unset -> in-memory graph, same schema
# NEO4J_USER=neo4j
# NEO4J_PASSWORD=evaluation
```

Optional Neo4j (browser UI at http://localhost:7474, user `neo4j` / password `evaluation`):

```bash
docker compose -f docker-compose.neo4j.yml up -d
```

## 3. Start

Terminal 1 — backend on :8000 (creates `.venv` and installs deps on first run):

```bash
./scripts/dev.sh
```

Terminal 2 — frontend on :5173:

```bash
cd frontend && npm install && npm run dev
```

Open **http://localhost:5173/evaluate**.

## 4. Run an evaluation

1. **Evaluate** page: click **check which models this key can call** — every platform model gets
   a tiny test request and shows up as ✓ (click to add) or ✗ 403. Then pick models from the
   dropdown (open-source platform models first, then the 🇨🇳 / 🇺🇸 catalog) or type any model id.
   Add several to compare them in one go.
2. Tick the persona agents and benchmarks to use, set items per benchmark, turns per agent, and
   the benchmark/agent weight (default 50/50).
3. Press **Run evaluation**. A three-step tracker shows *benchmark evaluation → simulated agents
   testing → scoring* with percent, elapsed time, an ETA (`~` while it is still an estimate) and
   tokens spent so far; each agent row shows its own 🤖 model / 🗣 simulator token counts live.
4. Click **Open results** when a session finishes. You get:
   - the **final score** and the two session scores it is built from,
   - every agent's **conversation with the model** and its **feedback** (ratings radar, summary,
     highlights, complaints, would-use-again),
   - the per-item **benchmark** results,
   - **Tokens & timing**: total / model-under-test / simulator tokens, seconds per stage, tokens
     per benchmark, and per agent per conversation round,
   - the **Neo4j graph** of the session (model at the centre, one spoke per agent, turns along
     the spoke, feedback beyond) plus the Cypher — live and editable when Neo4j is connected.

## 5. Manage and rank

- **Sessions** — list, filter by model, re-run, delete (also removes the session's graph data).
- **Rankings** — our own leaderboard across all completed sessions, with CN vs US averages.
- **Agents** — the five built-in personalities; import your own by pasting JSON or uploading a
  file. Try `Demo/personas/extra_personas.json`. Required fields are `name` and
  `scenario.opening_message`; everything else has defaults.

## 6. Use real benchmark data

The bundled benchmark files are small sample subsets so the app works offline. Replace them with
real rows from Hugging Face (no token needed):

```bash
.venv/bin/python scripts/fetch_benchmarks.py --rows 100
```

## 7. Same thing from the terminal

```bash
curl -N -X POST localhost:8000/api/eval/run/stream -H 'Content-Type: application/json' \
  -d '{"models":["moonshotai/kimi-k2.6","openai/gpt-5"],"items_per_benchmark":8,"agent_turns":3}'

curl localhost:8000/api/eval/rankings
curl localhost:8000/api/eval/sessions/<id>/graph
```

## Troubleshooting

- A model shows **✗ 403** in the access check — the key's plan does not include it; ask Canopy
  Wave to unlock it or pick another. On the demo key only `minimax/minimax-m3` and
  `moonshotai/kimi-k2.6` answer.
- **GSM8K items are slow** (30–60 s each) — the model is asked to reason step by step with up to
  1200 tokens; lower *items per benchmark* or untick GSM8K for quick runs.

- `env_loader: missing required environment variables ['CANOPYWAVE_API_KEY']` — create the `.env`
  (step 2). For a credit-free demo set it to `mock`.
- The Evaluate page shows a **mock mode** pill — the key is `mock` or `EVAL_MOCK=1`; scores are
  synthetic but deterministic.
- The graph badge says **in-memory** — `NEO4J_URI` is unset or Neo4j is unreachable; the service
  keeps working and stores the graph in `services/court-orchestrator/var/graph.json`.
- Tests: `cd services/court-orchestrator && CANOPYWAVE_API_KEY=test-key ../../.venv/bin/python -m pytest tests -q`
