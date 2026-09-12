import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useEvalStore, type RunProgress } from '../store'
import { REGION_FLAG } from '../types'
import { ScoreBar, ScoreRing, fmt } from '../components/ScoreTile'

const STAGE_LABEL: Record<string, string> = {
  queued: 'queued',
  benchmarks: '① benchmark session running…',
  agents: '② persona agents talking to the model…',
  scoring: 'scoring…',
  done: 'done',
  error: 'error',
}

export default function EvaluatePage() {
  const s = useEvalStore()
  const [modelInput, setModelInput] = useState('')
  useEffect(() => {
    void s.load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const catalogByRegion = useMemo(() => {
    const groups: Record<string, { id: string; vendor: string }[]> = {}
    for (const m of s.meta?.catalog ?? []) (groups[m.region] ??= []).push(m)
    return groups
  }, [s.meta])
  const platformOnly = useMemo(() => {
    const inCatalog = new Set((s.meta?.catalog ?? []).map((m) => m.id))
    return (s.meta?.platform_models ?? []).filter((m) => !inCatalog.has(m))
  }, [s.meta])

  const add = (m: string) => {
    s.addModel(m)
    setModelInput('')
  }
  const canRun = s.selectedModels.length > 0 && s.agentIds.length + s.benchmarkNames.length > 0 && !s.running

  return (
    <div className="page two-col">
      <section className="panel form-panel">
        <h2>Evaluate models</h2>
        <p className="muted">
          Each model gets one session: <b>{Math.round(s.benchmarkWeight * 100)}%</b> open-source benchmarks +{' '}
          <b>{Math.round((1 - s.benchmarkWeight) * 100)}%</b> feedback from persona agents that actually use it.
          {s.meta?.mock_mode && <span className="pill pill-warn"> mock mode — no inference calls</span>}
        </p>
        {s.loadError && <div className="error-text">{s.loadError}</div>}

        <label className="field-label">Model name(s)</label>
        <div className="model-input-row">
          <input
            className="field-input"
            list="model-catalog"
            placeholder="type a model id, e.g. deepseek-ai/deepseek-v3.2"
            value={modelInput}
            onChange={(e) => setModelInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && add(modelInput)}
          />
          <datalist id="model-catalog">
            {(s.meta?.catalog ?? []).map((m) => <option key={m.id} value={m.id}>{m.vendor} · {m.region}</option>)}
            {platformOnly.map((m) => <option key={m} value={m}>platform</option>)}
          </datalist>
          <select className="field-input" value="" onChange={(e) => e.target.value && add(e.target.value)}>
            <option value="">＋ pick from dropdown</option>
            {Object.entries(catalogByRegion).map(([region, models]) => (
              <optgroup key={region} label={`${REGION_FLAG[region] ?? ''} ${region === 'CN' ? 'Chinese models' : region === 'US' ? 'US models' : region}`}>
                {models.map((m) => <option key={m.id} value={m.id}>{m.id} — {m.vendor}</option>)}
              </optgroup>
            ))}
            {platformOnly.length > 0 && (
              <optgroup label="⚡ available on platform">
                {platformOnly.map((m) => <option key={m} value={m}>{m}</option>)}
              </optgroup>
            )}
          </select>
          <button className="run-button small" onClick={() => add(modelInput)} disabled={!modelInput.trim()}>Add</button>
        </div>
        <div className="chips">
          {s.selectedModels.length === 0 && <span className="muted">No models selected yet.</span>}
          {s.selectedModels.map((m) => (
            <span key={m} className="chip">
              {m} <button className="link-button" onClick={() => s.removeModel(m)} title="remove">✕</button>
            </span>
          ))}
        </div>

        <div className="split">
          <div>
            <label className="field-label">Persona agents ({s.agentIds.length}/{s.personas.length}) <Link to="/agents" className="muted small">manage →</Link></label>
            {s.personas.map((p) => (
              <label key={p.id} className="check">
                <input type="checkbox" checked={s.agentIds.includes(p.id)} onChange={() => s.toggleAgent(p.id)} />
                <span>{p.avatar} <b>{p.name}</b> <span className="muted">— {p.tagline}</span></span>
              </label>
            ))}
          </div>
          <div>
            <label className="field-label">Benchmarks ({s.benchmarkNames.length}/{s.meta?.benchmarks.length ?? 0})</label>
            {(s.meta?.benchmarks ?? []).map((b) => (
              <label key={b.name} className="check" title={b.description}>
                <input type="checkbox" checked={s.benchmarkNames.includes(b.name)} onChange={() => s.toggleBenchmark(b.name)} />
                <span><b>{b.display_name}</b> <span className="muted">— {b.item_count} items{b.bundled_sample ? ' (sample)' : ''}</span></span>
              </label>
            ))}
          </div>
        </div>

        <div className="sliders">
          <label>
            <span>Items per benchmark: <b>{s.itemsPerBenchmark}</b></span>
            <input type="range" min={1} max={s.meta?.defaults.max_items_per_benchmark ?? 50} value={s.itemsPerBenchmark} onChange={(e) => s.setNumber('itemsPerBenchmark', Number(e.target.value))} />
          </label>
          <label>
            <span>User turns per agent: <b>{s.agentTurns}</b></span>
            <input type="range" min={1} max={s.meta?.defaults.max_agent_turns ?? 6} value={s.agentTurns} onChange={(e) => s.setNumber('agentTurns', Number(e.target.value))} />
          </label>
          <label>
            <span>Weight — benchmarks <b>{Math.round(s.benchmarkWeight * 100)}%</b> / agents <b>{Math.round((1 - s.benchmarkWeight) * 100)}%</b></span>
            <input type="range" min={0} max={100} step={5} value={Math.round(s.benchmarkWeight * 100)} onChange={(e) => s.setNumber('benchmarkWeight', Number(e.target.value) / 100)} />
          </label>
        </div>

        <label className="field-label">Session label (optional)</label>
        <input className="field-input" value={s.label} onChange={(e) => s.setLabel(e.target.value)} placeholder="e.g. sept-2026 CN vs US round 1" />

        <div className="form-actions">
          <button className="run-button" disabled={!canRun} onClick={() => void s.startRun()}>
            {s.running ? 'Evaluating…' : `▶ Run evaluation${s.selectedModels.length > 1 ? ` (${s.selectedModels.length} models)` : ''}`}
          </button>
          <span className="muted small">simulator: {s.meta?.simulator_model ?? '…'} · graph: {s.meta?.graph.backend ?? '…'}</span>
        </div>
        {s.runError && <div className="error-text">{s.runError}</div>}
      </section>

      <section className="panel progress-panel">
        <h2>Live progress</h2>
        {s.runs.length === 0 && <p className="muted">Runs appear here as soon as you start one. Benchmark items and agent turns stream in live.</p>}
        {s.runs.map((run) => <RunCard key={run.sessionId} run={run} />)}
        {s.log.length > 0 && (
          <details className="log">
            <summary>event log ({s.log.length})</summary>
            <pre>{s.log.join('\n')}</pre>
          </details>
        )}
      </section>
    </div>
  )
}

function RunCard({ run }: { run: RunProgress }) {
  const benches = Object.values(run.benchmarks)
  const agents = Object.values(run.agents)
  const done = run.session
  return (
    <div className={`run-card stage-${run.stage}`}>
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
              <div>agents <b>{fmt(done.agent_score)}</b></div>
              <Link className="run-button small" to={`/sessions/${done.id}`}>Open results →</Link>
            </div>
          </div>
        ) : (
          <span className="spinner" />
        )}
      </div>
      <div className="run-body">
        <div>
          <div className="field-label">① Benchmark session</div>
          {benches.length === 0 && <div className="muted small">waiting…</div>}
          {benches.map((b) => (
            <div key={b.name} className="bench-row">
              <span className="bench-name">{b.name}</span>
              <ScoreBar value={b.total ? (b.done / b.total) * 100 : 0} color={b.score != null ? undefined : 'var(--accent-2)'} />
              <span className="small muted">{b.score != null ? `${b.score}% (${b.correct}/${b.total})` : `${b.done}/${b.total || '?'} · ${b.correct} ✓`}</span>
            </div>
          ))}
        </div>
        <div>
          <div className="field-label">② Agent session</div>
          {agents.map((a) => {
            const last = a.turns[a.turns.length - 1]
            return (
              <div key={a.id} className={`agent-row agent-${a.status}`}>
                <span className="agent-avatar">{a.avatar}</span>
                <div className="agent-line">
                  <div><b>{a.name}</b> <span className="muted small">{a.status === 'waiting' ? 'waiting' : a.status === 'talking' ? `turn ${a.turns.length}` : `scored ${a.score}/100`}</span></div>
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
