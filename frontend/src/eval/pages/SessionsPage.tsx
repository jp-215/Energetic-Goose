import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { deleteSession, fetchSessions } from '../api'
import { fmt, scoreColor } from '../components/ScoreTile'
import { useEvalStore } from '../store'
import { REGION_FLAG, type SessionSummary } from '../types'

export default function SessionsPage() {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [filter, setFilter] = useState('')
  const [error, setError] = useState<string | null>(null)
  const rerun = useEvalStore((s) => s.rerun)
  const running = useEvalStore((s) => s.running)
  const navigate = useNavigate()

  const load = () => fetchSessions().then((r) => setSessions(r.sessions)).catch((e) => setError(String(e)))
  useEffect(() => {
    void load()
    const t = window.setInterval(() => void load(), 4000)
    return () => window.clearInterval(t)
  }, [])

  const models = useMemo(() => [...new Set(sessions.map((s) => s.model))].sort(), [sessions])
  const visible = filter ? sessions.filter((s) => s.model === filter) : sessions

  return (
    <div className="page">
      <div className="session-head">
        <h2>Sessions <span className="muted small">({sessions.length})</span></h2>
        <div className="head-actions">
          <select className="field-input" value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">all models</option>
            {models.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          <Link className="run-button small" to="/evaluate">＋ New evaluation</Link>
        </div>
      </div>
      {error && <div className="error-text">{error}</div>}
      <div className="panel table-panel">
        <table className="data-table">
          <thead>
            <tr>
              <th>model</th><th>label</th><th>created</th><th>status</th>
              <th className="num">bench</th><th className="num">agents</th><th className="num">final</th><th></th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && <tr><td colSpan={8} className="muted">No sessions yet. <Link to="/evaluate">Run one →</Link></td></tr>}
            {visible.map((s) => (
              <tr key={s.id} className="clickable" onClick={() => navigate(`/sessions/${s.id}`)}>
                <td>{REGION_FLAG[s.region] ?? ''} <b>{s.model}</b><div className="muted small">{s.id}</div></td>
                <td className="muted">{s.label || '—'}</td>
                <td className="small">{new Date(s.created_at).toLocaleString()}</td>
                <td><span className={`pill pill-${s.status}`}>{s.status === 'running' ? s.stage : s.status}</span></td>
                <td className="num">{fmt(s.benchmark_score)}</td>
                <td className="num">{fmt(s.agent_score)}</td>
                <td className="num" style={{ color: scoreColor(s.final_score), fontWeight: 700 }}>{fmt(s.final_score)}</td>
                <td className="actions" onClick={(e) => e.stopPropagation()}>
                  <button className="link-button" disabled={running} onClick={() => { navigate('/evaluate'); void rerun(s.id) }}>↻ rerun</button>
                  <button className="link-button danger" onClick={async () => { if (confirm(`Delete session ${s.id}?`)) { await deleteSession(s.id); void load() } }}>delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
