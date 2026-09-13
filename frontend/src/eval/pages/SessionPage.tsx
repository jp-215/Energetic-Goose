import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { deleteSession, fetchPapersGraph, fetchSession, fetchSessionGraph, runCypher } from '../api'
import GraphView from '../components/GraphView'
import PersonaAvatar from '../components/PersonaAvatar'
import PersonaModal from '../components/PersonaModal'
import ProgressStepper from '../components/ProgressStepper'
import RatingsRadar from '../components/RatingsRadar'
import { ScoreBar, ScoreRing, fmt, scoreColor } from '../components/ScoreTile'
import Transcript from '../components/Transcript'
import { useEvalStore } from '../store'
import { DIMENSIONS, REGION_FLAG, fmtDuration, fmtTokens, type AgentResult, type BenchmarkResult, type GraphResponse, type Session } from '../types'

export default function SessionPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const rerun = useEvalStore((s) => s.rerun)
  const personas = useEvalStore((s) => s.personas)
  const loadStore = useEvalStore((s) => s.load)
  const [openPersona, setOpenPersona] = useState<string | null>(null)
  const [session, setSession] = useState<Session | null>(null)
  const [graph, setGraph] = useState<GraphResponse | null>(null)
  const [papers, setPapers] = useState<GraphResponse | null>(null)
  const [papersNote, setPapersNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [params, setParams] = useSearchParams()
  const tabParam = params.get('tab')
  type Tab = 'agents' | 'benchmarks' | 'tokens'
  const tab: Tab = tabParam === 'benchmarks' || tabParam === 'tokens' ? tabParam : 'agents'
  const setTab = (t: Tab) => setParams(t === 'agents' ? {} : { tab: t }, { replace: true })

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
    void loadStore()
    let timer: number | undefined
    const tick = async () => {
      const s = await reload()
      if (s && s.status === 'running') timer = window.setTimeout(tick, 2500)
    }
    void tick()
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])
  useEffect(() => {
    // The papers corpus is shared across sessions: fetch once, failures are non-fatal.
    fetchPapersGraph()
      .then(setPapers)
      .catch((err) => setPapersNote(err instanceof Error ? err.message : String(err)))
  }, [])

  if (error) return <div className="page"><div className="error-text">{error}</div></div>
  if (!session) return <div className="page muted">loading session…</div>

  const w = session.weights
  const excluded = session.agents.filter((a) => a.status === 'error')
  const graded = session.agents.length - excluded.length
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
      {session.progress && (session.status === 'running' || session.status === 'error') && (
        <section className="panel"><ProgressStepper progress={session.progress} /></section>
      )}

      <section className="panel score-panel">
        <ScoreRing score={session.final_score} label="Final score" size={150} sub={`${Math.round(w.benchmark * 100)}% × bench + ${Math.round(w.agents * 100)}% × agents`} />
        <div className="score-eq">=</div>
        <ScoreRing score={session.benchmark_score} label="① Benchmark session" size={120} sub={`${session.benchmarks.length} benchmarks · ${session.config.items_per_benchmark} items each`} />
        <div className="score-eq">+</div>
        <ScoreRing score={session.agent_score} label="② Agent session" size={120} sub={`${graded}/${session.config.agent_ids.length} users graded · ${session.config.agent_turns} turns each`} />
        <div className="formula muted small">
          final = {w.benchmark} × {fmt(session.benchmark_score)} + {w.agents} × {fmt(session.agent_score)} = <b>{fmt(session.final_score)}</b>
          {session.timings && <> · took <b>{fmtDuration(session.timings.total_s)}</b></>}
          {session.tokens && <> · <b>{fmtTokens(session.tokens.total.total)}</b> tokens{session.tokens.total.estimated ? ' (est.)' : ''}</>}
        </div>
        {excluded.length > 0 && (
          <div className="warn-strip">
            ⚠ {excluded.length} of {session.agents.length} simulated users could not deliver a verdict ({excluded.map((a) => a.agent_name).join(', ')}) and are excluded from the agent score. Open a user for the error; re-run to try again.
          </div>
        )}
      </section>

      <section className="panel">
        <div className="card-title">Simulated users <span className="muted small">click an avatar for their personality and verdict</span></div>
        <div className="avatar-grid">
          {session.config.agent_ids.map((id) => {
            const p = personas.find((x) => x.id === id)
            const r = session.agents.find((a) => a.agent_id === id)
            const base = p ?? (r ? { id, name: r.agent_name, avatar: r.avatar, tagline: r.scenario_title } : { id, name: id, avatar: '🙂', tagline: '' })
            return <PersonaAvatar key={id} persona={base} score={r?.score ?? null} status={r ? r.status : session.status === 'running' && session.stage === 'agents' ? 'talking' : 'waiting'} onClick={() => setOpenPersona(id)} />
          })}
        </div>
      </section>

      <section className="panel graph-section">
        <div className="card-title">
          Neo4j interaction graph
          <span className={`pill ${graph?.backend === 'neo4j' ? 'pill-ok' : 'pill-warn'}`}>{graph?.backend === 'neo4j' ? 'Neo4j' : 'in-memory fallback'}</span>
          <span className="muted small">{graph ? `${graph.nodes.length} nodes · ${graph.relationships.length} relationships` : 'loading…'} · model at the centre, one spoke per user, turns along the spoke, feedback beyond</span>
        </div>
        {graph && <GraphPanel graph={graph} />}
      </section>

      <section className="panel graph-section">
        <div className="card-title">
          Neo4j papers &amp; knowledge graph
          <span className={`pill ${papers ? 'pill-ok' : 'pill-warn'}`}>{papers ? 'shared Neo4j instance' : 'unavailable'}</span>
          <span className="muted small">
            {papers
              ? `${papers.nodes.filter((n) => n.label === 'Paper').length} papers · ${papers.nodes.filter((n) => n.label === 'KnowledgeNode').length} knowledge nodes · papers cluster around the topic they belong to; SUPPORTS / SHARES_AUTHOR edges cross clusters`
              : papersNote ?? 'loading…'}
          </span>
        </div>
        {papers && <GraphPanel graph={papers} cypherTitle="Cypher for this graph" />}
      </section>

      <div className="tabs">
        <button className={tab === 'agents' ? 'active' : ''} onClick={() => setTab('agents')}>User feedback & transcripts ({session.agents.length})</button>
        <button className={tab === 'benchmarks' ? 'active' : ''} onClick={() => setTab('benchmarks')}>Benchmarks ({session.benchmarks.length})</button>
        <button className={tab === 'tokens' ? 'active' : ''} onClick={() => setTab('tokens')}>Tokens & timing</button>
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
      {tab === 'tokens' && <TokensPanel session={session} />}
      {openPersona && (() => {
        const p = personas.find((x) => x.id === openPersona)
        const r = session.agents.find((a) => a.agent_id === openPersona) ?? null
        return p ? <PersonaModal persona={p} result={r} onClose={() => setOpenPersona(null)} /> : null
      })()}
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
          <div className="muted small">
            scenario: {agent.scenario_title} · {agent.turns.length} turns
            {agent.tokens && <> · 🤖 {fmtTokens(agent.tokens.target.total)} · 🗣 {fmtTokens(agent.tokens.simulator.total)} tok</>}
          </div>
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

function GraphPanel({ graph, cypherTitle = 'Cypher for this session' }: { graph: GraphResponse; cypherTitle?: string }) {
  const [query, setQuery] = useState(graph.cypher)
  const [result, setResult] = useState<string | null>(null)
  const isNeo4j = graph.backend === 'neo4j'
  return (
    <div>
      <GraphView graph={graph} />
      <details className="cypher">
        <summary>{cypherTitle} {isNeo4j ? '(editable, read-only queries)' : ''}</summary>
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

function TokensPanel({ session }: { session: Session }) {
  const t = session.tokens
  const tm = session.timings
  if (!t) return <div className="panel muted">Token accounting appears when the session finishes scoring.</div>
  const Tile = ({ label, value, sub }: { label: string; value: string; sub?: string }) => (
    <div className="tile"><div className="tile-value">{value}</div><div className="tile-label">{label}</div>{sub && <div className="muted small">{sub}</div>}</div>
  )
  return (
    <div className="bench-grid">
      <div className="tiles">
        <Tile label="total tokens" value={fmtTokens(t.total.total)} sub={`${fmtTokens(t.total.prompt)} prompt · ${fmtTokens(t.total.completion)} completion${t.total.estimated ? ' · estimated' : ''}`} />
        <Tile label="model under test" value={fmtTokens(t.model_under_test.total)} sub="benchmark answers + replies to agents" />
        <Tile label="simulator (personas)" value={fmtTokens(t.agents.simulator.total)} sub={`${session.simulator_model}`} />
        <Tile label="benchmark session" value={fmtTokens(t.benchmarks.total)} sub={tm ? `${fmtDuration(tm.benchmarks_s)}` : ''} />
        <Tile label="agent session" value={fmtTokens(t.agents.total.total)} sub={tm ? `${fmtDuration(tm.agents_s)}` : ''} />
        <Tile label="total time" value={fmtDuration(tm?.total_s)} sub="wall clock" />
      </div>

      <div className="panel">
        <h3>Per benchmark</h3>
        <table className="data-table compact">
          <thead><tr><th>benchmark</th><th className="num">items</th><th className="num">score</th><th className="num">prompt</th><th className="num">completion</th><th className="num">total</th><th className="num">avg latency</th></tr></thead>
          <tbody>
            {session.benchmarks.map((b) => (
              <tr key={b.name}><td>{b.display_name}</td><td className="num">{b.total}</td><td className="num">{b.score}%</td><td className="num">{fmtTokens(b.tokens.prompt)}</td><td className="num">{fmtTokens(b.tokens.completion)}</td><td className="num"><b>{fmtTokens(b.tokens.total)}</b></td><td className="num">{b.avg_latency_ms} ms</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h3>Per agent, per round</h3>
        <p className="muted small">🤖 = tokens spent by the model under test · 🗣 = tokens spent by the simulator playing the persona (its follow-up messages and the feedback form). Round 1's persona message is scripted, so it costs nothing.</p>
        <table className="data-table compact">
          <thead><tr><th>agent</th><th>round</th><th className="num">🗣 simulator</th><th className="num">🤖 model</th><th className="num">total</th><th className="num">latency</th></tr></thead>
          <tbody>
            {session.agents.map((a) => (
              <>
                <tr key={a.agent_id} className="row-group">
                  <td><b>{a.avatar} {a.agent_name}</b> <span className="muted small">score {a.score}</span></td>
                  <td className="muted">all rounds + feedback</td>
                  <td className="num"><b>{fmtTokens(a.tokens.simulator.total)}</b></td>
                  <td className="num"><b>{fmtTokens(a.tokens.target.total)}</b></td>
                  <td className="num"><b>{fmtTokens(a.tokens.total.total)}</b></td>
                  <td className="num">{fmtDuration(a.turns.reduce((acc, x) => acc + x.latency_ms, 0) / 1000)}</td>
                </tr>
                {a.rounds.map((r) => (
                  <tr key={`${a.agent_id}-${r.round}`} className="row-sub">
                    <td></td><td className="muted">round {r.round}</td>
                    <td className="num">{fmtTokens(r.simulator_tokens)}</td><td className="num">{fmtTokens(r.target_tokens)}</td><td className="num">{fmtTokens(r.total_tokens)}</td><td className="num">{r.latency_ms} ms</td>
                  </tr>
                ))}
                <tr key={`${a.agent_id}-fb`} className="row-sub">
                  <td></td><td className="muted">feedback form</td>
                  <td className="num">{fmtTokens(a.tokens.feedback.total)}</td><td className="num">—</td><td className="num">{fmtTokens(a.tokens.feedback.total)}</td><td className="num"></td>
                </tr>
              </>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
