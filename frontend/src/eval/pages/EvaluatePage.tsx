import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchSessions } from '../api'
import PersonaAvatar from '../components/PersonaAvatar'
import PersonaModal from '../components/PersonaModal'
import ProgressStepper from '../components/ProgressStepper'
import { ScoreBar, ScoreRing, fmt, scoreColor } from '../components/ScoreTile'
import { useEvalStore, type RunProgress } from '../store'
import { REGION_FLAG, fmtTokens, type SessionSummary } from '../types'

const STAGE_LABEL: Record<string, string> = {
  queued: 'queued',
  benchmarks: '① benchmark evaluation running…',
  agents: '② simulated users are testing the model…',
  scoring: '③ scoring…',
  done: 'done',
  error: 'error',
}

export default function EvaluatePage() {
  const s = useEvalStore()
  const [modelInput, setModelInput] = useState('')
  const [openPersona, setOpenPersona] = useState<string | null>(null)
  const [recent, setRecent] = useState<SessionSummary[]>([])
  useEffect(() => {
    void s.load()
    fetchSessions().then((r) => setRecent(r.sessions.slice(0, 6))).catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.running])

  const catalogByRegion = useMemo(() => {
    const groups: Record<string, { id: string; vendor: string }[]> = {}
    for (const m of s.meta?.catalog ?? []) (groups[m.region] ??= []).push(m)
    return groups
  }, [s.meta])

  const add = (m: string) => {
    s.addModel(m)
    setModelInput('')
  }
  const probed = Object.keys(s.probe).length > 0
  const accessible = Object.values(s.probe).filter((r) => r.accessible).map((r) => r.model)
  const mark = (id: string) => (!probed ? '' : s.probe[id] ? (s.probe[id].accessible ? ' ✓' : ' ✗ 403') : '')

  const benchItems = (s.meta?.benchmarks ?? []).filter((b) => s.benchmarkNames.includes(b.name)).reduce((acc, b) => acc + Math.min(s.itemsPerBenchmark, b.item_count), 0)
  const agentCalls = s.agentIds.length * s.agentTurns * 2
  const callsPerModel = benchItems + agentCalls
  const canRun = s.selectedModels.length > 0 && callsPerModel > 0 && !s.running
  const persona = openPersona ? s.personas.find((p) => p.id === openPersona) : null

  return (
    <div className="page arena">
      <header className="arena-hero">
        <div>
          <div className="eyebrow">Model Evaluation Arena</div>
          <h2>Benchmarks × simulated users → one score</h2>
          <p className="muted">
            Every model gets a session: <b>{Math.round(s.benchmarkWeight * 100)}%</b> open-source benchmarks, <b>{Math.round((1 - s.benchmarkWeight) * 100)}%</b> feedback from people with personalities who actually use it.
            Everything they do is mapped in Neo4j.
          </p>
        </div>
        <div className="hero-pills">
          <span className="pill">⚡ Canopy Wave</span>
          <span className="pill">🗣 simulator · {s.meta?.simulator_model ?? '…'}</span>
          <span className={`pill ${s.meta?.graph.backend === 'neo4j' ? 'pill-ok' : 'pill-warn'}`}>◉ graph · {s.meta?.graph.backend ?? '…'}</span>
          {s.meta?.mock_mode && <span className="pill pill-warn">mock mode</span>}
        </div>
      </header>
      {s.loadError && <div className="error-text">{s.loadError}</div>}

      <div className="arena-grid">
        {/* ---------------- 1 · models ---------------- */}
        <section className="panel arena-card">
          <div className="card-title"><span className="step-no">1</span> Models to evaluate</div>
          <div className="model-input-row">
            <input
              className="field-input"
              list="model-catalog"
              placeholder="type a model id…"
              value={modelInput}
              onChange={(e) => setModelInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && add(modelInput)}
            />
            <datalist id="model-catalog">
              {(s.meta?.platform_models ?? []).map((m) => <option key={m} value={m}>platform</option>)}
              {(s.meta?.catalog ?? []).map((m) => <option key={m.id} value={m.id}>{m.vendor} · {m.region}</option>)}
            </datalist>
            <select className="field-input" value="" onChange={(e) => e.target.value && add(e.target.value)}>
              <option value="">＋ dropdown</option>
              {(s.meta?.platform_models.length ?? 0) > 0 && (
                <optgroup label="⚡ open-source models on this platform">
                  {s.meta!.platform_models.map((m) => <option key={m} value={m}>{m}{mark(m)}</option>)}
                </optgroup>
              )}
              {Object.entries(catalogByRegion).map(([region, models]) => (
                <optgroup key={region} label={`${REGION_FLAG[region] ?? ''} ${region === 'CN' ? 'Chinese models' : region === 'US' ? 'US models' : region} (catalog)`}>
                  {models.map((m) => <option key={m.id} value={m.id}>{m.id} — {m.vendor}{mark(m.id)}</option>)}
                </optgroup>
              ))}
            </select>
          </div>
          <button className="link-button" onClick={() => void s.runProbe()} disabled={s.probing || !!s.meta?.mock_mode}>
            {s.probing ? 'checking access…' : probed ? `↻ re-check (${accessible.length}/${Object.keys(s.probe).length} usable on this key)` : '⚡ check which models this key can call'}
          </button>
          {probed && (
            <div className="chips">
              {Object.values(s.probe).map((r) => (
                <button key={r.model} className={`chip chip-button ${r.accessible ? 'chip-ok' : 'chip-off'}`} disabled={!r.accessible}
                  title={r.accessible ? `${r.latency_ms} ms — click to add` : r.error ?? 'not accessible'} onClick={() => add(r.model)}>
                  {r.accessible ? '✓' : '✗'} {r.model}
                </button>
              ))}
            </div>
          )}
          <div className="selected-models">
            {s.selectedModels.length === 0 && <div className="muted small empty">Nothing selected yet — add one or more model ids above.</div>}
            {s.selectedModels.map((m) => {
              const region = s.meta?.catalog.find((c) => c.id === m)?.region ?? (m.split('/')[0] ? '?' : '?')
              return (
                <div key={m} className="model-row">
                  <span className="model-flag">{REGION_FLAG[region] ?? '🌐'}</span>
                  <span className="grow mono">{m}</span>
                  {probed && s.probe[m] && <span className={`pill ${s.probe[m].accessible ? 'pill-ok' : 'pill-err'}`}>{s.probe[m].accessible ? 'ok' : '403'}</span>}
                  <button className="link-button danger" onClick={() => s.removeModel(m)}>remove</button>
                </div>
              )
            })}
          </div>
        </section>

        {/* ---------------- 2 · simulated users ---------------- */}
        <section className="panel arena-card">
          <div className="card-title">
            <span className="step-no">2</span> Simulated users
            <span className="muted small">{s.agentIds.length}/{s.personas.length} in run · click an avatar to meet them</span>
            <Link to="/agents" className="link-button">manage / import →</Link>
          </div>
          <div className="avatar-grid">
            {s.personas.map((p) => (
              <PersonaAvatar key={p.id} persona={p} selected={s.agentIds.includes(p.id)} onClick={() => setOpenPersona(p.id)} onToggle={() => s.toggleAgent(p.id)} />
            ))}
          </div>
          <div className="sliders">
            <label>
              <span>Conversation length · <b>{s.agentTurns}</b> user turn{s.agentTurns > 1 ? 's' : ''} each</span>
              <input type="range" min={1} max={s.meta?.defaults.max_agent_turns ?? 6} value={s.agentTurns} onChange={(e) => s.setNumber('agentTurns', Number(e.target.value))} />
            </label>
          </div>
        </section>

        {/* ---------------- 3 · benchmarks & weights ---------------- */}
        <section className="panel arena-card">
          <div className="card-title"><span className="step-no">3</span> Benchmarks &amp; weights</div>
          <div className="chips">
            {(s.meta?.benchmarks ?? []).map((b) => {
              const on = s.benchmarkNames.includes(b.name)
              return (
                <button key={b.name} className={`chip chip-button ${on ? 'chip-on' : ''}`} title={b.description} onClick={() => s.toggleBenchmark(b.name)}>
                  {on ? '✓ ' : ''}{b.display_name} <span className="muted">· {b.item_count}{b.bundled_sample ? ' sample' : ''}</span>
                </button>
              )
            })}
          </div>
          <div className="sliders">
            <label>
              <span>Items per benchmark · <b>{s.itemsPerBenchmark}</b></span>
              <input type="range" min={1} max={s.meta?.defaults.max_items_per_benchmark ?? 50} value={s.itemsPerBenchmark} onChange={(e) => s.setNumber('itemsPerBenchmark', Number(e.target.value))} />
            </label>
            <label>
              <span>Score weight</span>
              <input type="range" min={0} max={100} step={5} value={Math.round(s.benchmarkWeight * 100)} onChange={(e) => s.setNumber('benchmarkWeight', Number(e.target.value) / 100)} />
            </label>
          </div>
          <div className="weight-bar">
            <div className="weight-bench" style={{ width: `${s.benchmarkWeight * 100}%` }}>benchmarks {Math.round(s.benchmarkWeight * 100)}%</div>
            <div className="weight-agents" style={{ width: `${(1 - s.benchmarkWeight) * 100}%` }}>users {Math.round((1 - s.benchmarkWeight) * 100)}%</div>
          </div>
          <label className="field-label">Session label (optional)</label>
          <input className="field-input" value={s.label} onChange={(e) => s.setLabel(e.target.value)} placeholder="e.g. sept-2026 CN vs US round 1" />
        </section>
      </div>

      {/* ---------------- run bar ---------------- */}
      <div className="run-bar panel">
        <div className="run-summary">
          <b>{s.selectedModels.length}</b> model{s.selectedModels.length === 1 ? '' : 's'} × (
          <b>{benchItems}</b> benchmark items + <b>{s.agentIds.length}</b> users × <b>{s.agentTurns}</b> turns) ≈{' '}
          <b>{callsPerModel * Math.max(1, s.selectedModels.length)}</b> model calls
        </div>
        <button className="run-button big" disabled={!canRun} onClick={() => void s.startRun()}>
          {s.running ? '⏳ Evaluating…' : '▶ Run evaluation'}
        </button>
      </div>
      {s.runError && <div className="error-text">{s.runError}</div>}

      {/* ---------------- live progress ---------------- */}
      <section className="progress-zone">
        {s.runs.length === 0 ? (
          <div className="arena-grid">
            <div className="panel howto">
              <div className="card-title">How a session runs</div>
              <ol className="pipeline">
                <li><b>Benchmark evaluation</b><span className="muted">MMLU · GSM8K · ARC · TruthfulQA · HellaSwag</span></li>
                <li><b>Simulated users test the model</b><span className="muted">multi-turn conversations, then a feedback form each</span></li>
                <li><b>Scoring</b><span className="muted">final = w × benchmarks + (1 − w) × users</span></li>
              </ol>
              <p className="muted small">Progress, ETA and token spend stream in live; the whole interaction is mirrored to Neo4j.</p>
            </div>
            <div className="panel howto span-2">
              <div className="card-title">Recent sessions <Link to="/sessions" className="link-button">all →</Link></div>
              {recent.length === 0 && <div className="muted small">No sessions yet.</div>}
              {recent.map((r) => (
                <Link key={r.id} to={`/sessions/${r.id}`} className="recent-row">
                  <span>{REGION_FLAG[r.region] ?? ''} <b>{r.model}</b> <span className="muted small">{r.label || r.id}</span></span>
                  <span className={`pill pill-${r.status}`}>{r.status === 'running' ? `${r.percent?.toFixed(0) ?? 0}%` : r.status}</span>
                  <span style={{ color: scoreColor(r.final_score), fontWeight: 700 }}>{fmt(r.final_score)}</span>
                </Link>
              ))}
            </div>
          </div>
        ) : (
          s.runs.map((run) => <RunCard key={run.sessionId} run={run} onPersona={setOpenPersona} />)
        )}
        {s.log.length > 0 && (
          <details className="log"><summary>event log ({s.log.length})</summary><pre>{s.log.join('\n')}</pre></details>
        )}
      </section>

      {persona && (
        <PersonaModal persona={persona} selected={s.agentIds.includes(persona.id)} onToggle={() => s.toggleAgent(persona.id)} onClose={() => setOpenPersona(null)} />
      )}
    </div>
  )
}

function RunCard({ run, onPersona }: { run: RunProgress; onPersona: (id: string) => void }) {
  const benches = Object.values(run.benchmarks)
  const agents = Object.values(run.agents)
  const done = run.session
  return (
    <div className={`run-card panel stage-${run.stage}`}>
      <div className="run-head">
        <div>
          <div className="run-model">{run.model}</div>
          <div className="muted small">session {run.sessionId} · {STAGE_LABEL[run.stage] ?? run.stage}</div>
        </div>
        {done ? (
          <div className="run-scores">
            <ScoreRing score={done.final_score} label="final" size={84} />
            <div className="mini-scores">
              <div>benchmarks <b>{fmt(done.benchmark_score)}</b></div>
              <div>users <b>{fmt(done.agent_score)}</b></div>
              <div className="muted">tokens <b>{fmtTokens(done.tokens?.total.total)}</b></div>
              <Link className="run-button small" to={`/sessions/${done.id}`}>Open results →</Link>
            </div>
          </div>
        ) : (
          <span className="spinner" />
        )}
      </div>
      {run.progress && <ProgressStepper progress={run.progress} />}
      <div className="run-body">
        <div>
          <div className="field-label">① Benchmark evaluation</div>
          {benches.length === 0 && <div className="muted small">waiting…</div>}
          {benches.map((b) => (
            <div key={b.name} className="bench-row">
              <span className="bench-name">{b.name}</span>
              <ScoreBar value={b.total ? (b.done / b.total) * 100 : 0} color={b.score != null ? undefined : 'var(--accent-2)'} />
              <span className="small muted">
                {b.score != null ? `${b.score}% (${b.correct}/${b.total})` : `${b.done}/${b.total || '?'} · ${b.correct} ✓`}
                {b.tokens > 0 && <> · {fmtTokens(b.tokens)} tok</>}
              </span>
            </div>
          ))}
        </div>
        <div>
          <div className="field-label">② Simulated users</div>
          <div className="avatar-grid tight">
            {agents.map((a) => (
              <PersonaAvatar key={a.id} persona={{ id: a.id, name: a.name, avatar: a.avatar, tagline: '' }} score={a.score} status={a.status} size={52} onClick={() => onPersona(a.id)} />
            ))}
          </div>
          {agents.map((a) => {
            const last = a.turns[a.turns.length - 1]
            const tok = a.tokens
            return (
              <div key={a.id} className={`agent-row agent-${a.status}`}>
                <span className="agent-avatar">{a.avatar}</span>
                <div className="agent-line">
                  <div>
                    <b>{a.name}</b>{' '}
                    <span className="muted small">
                      {a.status === 'waiting' ? 'waiting' : a.status === 'talking' ? `round ${last?.round ?? 0} · ${a.turns.length} msgs` : `scored ${a.score}/100`}
                      {' · '}
                      <span title="tokens spent by the model under test / by the simulator playing this persona">
                        🤖 {fmtTokens(tok ? tok.target.total : a.liveTokens.target)} · 🗣 {fmtTokens(tok ? tok.simulator.total : a.liveTokens.simulator)} tok
                      </span>
                    </span>
                  </div>
                  {last && a.status === 'talking' && <div className="muted small ellipsis">{last.role === 'user' ? '🗣 ' : '🤖 '}{last.content}</div>}
                  {a.feedback && <div className="small ellipsis">“{a.feedback.quote || a.feedback.summary}”</div>}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
