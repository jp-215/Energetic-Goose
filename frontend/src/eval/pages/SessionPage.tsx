import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { deleteSession, fetchSession, fetchSessionGraph, runCypher } from '../api'
import GraphView from '../components/GraphView'
import RatingsRadar from '../components/RatingsRadar'
import { ScoreBar, ScoreRing, fmt, scoreColor } from '../components/ScoreTile'
import Transcript from '../components/Transcript'
import { useEvalStore } from '../store'
import { DIMENSIONS, REGION_FLAG, type AgentResult, type BenchmarkResult, type GraphResponse, type Session } from '../types'

export default function SessionPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const rerun = useEvalStore((s) => s.rerun)
  const [session, setSession] = useState<Session | null>(null)
  const [graph, setGraph] = useState<GraphResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [params, setParams] = useSearchParams()
  const tabParam = params.get('tab')
  const tab: 'agents' | 'benchmarks' | 'graph' =
    tabParam === 'benchmarks' || tabParam === 'graph' ? tabParam : 'agents'
  const setTab = (t: 'agents' | 'benchmarks' | 'graph') => setParams(t === 'agents' ? {} : { tab: t }, { replace: true })

  const reload = async () => {
    try {
      const s = await fetchSession(id)
      setSession(s)
      setGraph(await fetchSessionGraph(id))
      return s
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      return null
    }
  }
  useEffect(() => {
    let timer: number | undefined
    const tick = async () => {
      const s = await reload()
      if (s && s.status === 'running') timer = window.setTimeout(tick, 2500)
    }
    void tick()
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  if (error) return <div className="page"><div className="error-text">{error}</div></div>
  if (!session) return <div className="page muted">loading session…</div>

  const w = session.weights
  return (
    <div className="page">
      <div className="session-head">
        <div>
          <div className="crumbs"><Link to="/sessions">sessions</Link> / {session.id}</div>
          <h2>{REGION_FLAG[session.region] ?? ''} {session.model} <span className={`pill pill-${session.status}`}>{session.status === 'running' ? session.stage : session.status}</span></h2>
          <div className="muted small">
            {session.label && <>“{session.label}” · </>}
            {new Date(session.created_at).toLocaleString()} · vendor {session.vendor} · simulator {session.simulator_model}
            {session.config.mock_mode && ' · mock mode'} · seed {session.config.seed}
          </div>
        </div>
        <div className="head-actions">
          <button className="run-button small" onClick={async () => { navigate('/evaluate'); void rerun(session.id) }}>↻ Re-run</button>
          <button className="close-button" onClick={async () => { if (confirm('Delete this session and its graph data?')) { await deleteSession(session.id); navigate('/sessions') } }}>Delete</button>
        </div>
      </div>
      {session.error && <div className="error-text">{session.error}</div>}

      <section className="panel score-panel">
        <ScoreRing score={session.final_score} label="Final score" size={150} sub={`${Math.round(w.benchmark * 100)}% × bench + ${Math.round(w.agents * 100)}% × agents`} />
        <div className="score-eq">=</div>
        <ScoreRing score={session.benchmark_score} label="① Benchmark session" size={120} sub={`${session.benchmarks.length} benchmarks · ${session.config.items_per_benchmark} items each`} />
        <div className="score-eq">+</div>
        <ScoreRing score={session.agent_score} label="② Agent session" size={120} sub={`${session.agents.length} personas · ${session.config.agent_turns} turns each`} />
        <div className="formula muted small">
          final = {w.benchmark} × {fmt(session.benchmark_score)} + {w.agents} × {fmt(session.agent_score)} = <b>{fmt(session.final_score)}</b>
        </div>
      </section>

      <div className="tabs">
        <button className={tab === 'agents' ? 'active' : ''} onClick={() => setTab('agents')}>Agent interactions & feedback ({session.agents.length})</button>
        <button className={tab === 'benchmarks' ? 'active' : ''} onClick={() => setTab('benchmarks')}>Benchmarks ({session.benchmarks.length})</button>
        <button className={tab === 'graph' ? 'active' : ''} onClick={() => setTab('graph')}>Neo4j graph {graph ? `(${graph.nodes.length} nodes · ${graph.relationships.length} rels)` : ''}</button>
      </div>

      {tab === 'agents' && (
        <div className="agent-grid">
          {session.agents.length === 0 && <div className="muted">Agents have not reported yet.</div>}
          {session.agents.map((a) => <AgentCard key={a.agent_id} agent={a} model={session.model} />)}
        </div>
      )}
      {tab === 'benchmarks' && (
        <div className="bench-grid">
          {session.benchmarks.length === 0 && <div className="muted">Benchmarks have not finished yet.</div>}
          {session.benchmarks.map((b) => <BenchmarkCard key={b.name} bench={b} />)}
        </div>
      )}
      {tab === 'graph' && graph && <GraphPanel graph={graph} />}
    </div>
  )
}

function AgentCard({ agent, model }: { agent: AgentResult; model: string }) {
  const [open, setOpen] = useState(false)
  const fb = agent.feedback
  return (
    <div className={`panel agent-card status-${agent.status}`}>
      <div className="agent-card-head">
        <div className="agent-avatar big">{agent.avatar}</div>
        <div className="grow">
          <div className="agent-name">{agent.agent_name}</div>
          <div className="muted small">scenario: {agent.scenario_title} · {agent.turns.length} turns</div>
        </div>
        <div className="agent-score" style={{ color: scoreColor(agent.score) }}>{fmt(agent.score)}<span className="muted small">/100</span></div>
      </div>
      {agent.error && <div className="error-text small">{agent.error}</div>}
      {fb && (
        <div className="feedback">
          <div className="feedback-radar">
            <RatingsRadar ratings={fb.ratings} priorities={agent.priorities} size={170} />
            <div className="muted small center">solid = ratings · dashed = what this persona cares about</div>
          </div>
          <div className="feedback-text">
            <div className="ratings-bars">
              {DIMENSIONS.map((d) => (
                <div key={d} className="rating-row">
                  <span className="rating-name">{d} <span className="muted">w {Math.round((agent.priorities[d] ?? 0) * 100)}%</span></span>
                  <ScoreBar value={fb.ratings[d] ?? 0} max={10} height={6} />
                  <span className="rating-val">{fb.ratings[d]}</span>
                </div>
              ))}
            </div>
            {fb.quote && <blockquote>“{fb.quote}”</blockquote>}
            <p>{fb.summary}</p>
            <div className="hl">
              {fb.highlights.map((h, i) => <span key={`h${i}`} className="pill pill-ok">＋ {h}</span>)}
              {fb.complaints.map((c, i) => <span key={`c${i}`} className="pill pill-err">− {c}</span>)}
              <span className={`pill ${fb.would_use_again ? 'pill-ok' : 'pill-err'}`}>{fb.would_use_again ? 'would use again' : 'would not use again'}</span>
            </div>
          </div>
        </div>
      )}
      <button className="link-button" onClick={() => setOpen(!open)}>{open ? '▾ hide' : '▸ show'} conversation</button>
      {open && <Transcript turns={agent.turns} agentName={agent.agent_name} avatar={agent.avatar} model={model} />}
    </div>
  )
}

function BenchmarkCard({ bench }: { bench: BenchmarkResult }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="panel bench-card">
      <div className="bench-head">
        <div className="grow">
          <div className="agent-name">{bench.display_name}</div>
          <div className="muted small">{bench.source} · {bench.task_type} · avg {bench.avg_latency_ms} ms{bench.errors ? ` · ${bench.errors} errors` : ''}</div>
        </div>
        <div className="agent-score" style={{ color: scoreColor(bench.score) }}>{bench.score}%<div className="muted small">{bench.correct}/{bench.total}</div></div>
      </div>
      <ScoreBar value={bench.score} />
      <button className="link-button" onClick={() => setOpen(!open)}>{open ? '▾ hide' : '▸ show'} items</button>
      {open && (
        <table className="items-table">
          <thead><tr><th></th><th>question</th><th>expected</th><th>model said</th></tr></thead>
          <tbody>
            {bench.items.map((it) => (
              <tr key={it.id} className={it.correct ? 'row-ok' : 'row-err'}>
                <td>{it.correct ? '✓' : '✗'}</td>
                <td>
                  <div>{it.question}</div>
                  {it.choices && <div className="muted small">{it.choices.map((c, i) => `${'ABCDEFGHIJ'[i]}) ${c}`).join('  ')}</div>}
                </td>
                <td>{it.expected}</td>
                <td title={it.response}>{it.predicted ?? <span className="muted">n/a</span>}{it.error && <div className="error-text small">{it.error}</div>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function GraphPanel({ graph }: { graph: GraphResponse }) {
  const [query, setQuery] = useState(graph.cypher)
  const [result, setResult] = useState<string | null>(null)
  const isNeo4j = graph.backend === 'neo4j'
  return (
    <div className="panel">
      <div className="graph-status">
        <span className={`pill ${isNeo4j ? 'pill-ok' : 'pill-warn'}`}>{isNeo4j ? 'Neo4j' : 'in-memory graph (set NEO4J_URI to use Neo4j)'}</span>
        <span className="muted small">Model at the centre · one spoke per persona agent · turns along the spoke · feedback beyond the agent · session + benchmarks above</span>
      </div>
      <GraphView graph={graph} />
      <details className="cypher">
        <summary>Cypher for this session {isNeo4j ? '(editable, read-only queries)' : ''}</summary>
        <textarea className="field-input mono" rows={7} value={query} onChange={(e) => setQuery(e.target.value)} readOnly={!isNeo4j} />
        {isNeo4j && (
          <button className="run-button small" onClick={async () => {
            try { setResult(JSON.stringify(await runCypher(query), null, 2)) } catch (err) { setResult(String(err)) }
          }}>Run query</button>
        )}
        {result && <pre className="log">{result}</pre>}
      </details>
    </div>
  )
}
