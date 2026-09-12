import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchRankings } from '../api'
import { ScoreBar, fmt, scoreColor } from '../components/ScoreTile'
import { REGION_FLAG, type RankingEntry } from '../types'

type SortKey = 'avg_final' | 'best_final' | 'latest_final' | 'avg_benchmark' | 'avg_agents' | 'sessions'

export default function RankingsPage() {
  const [rows, setRows] = useState<RankingEntry[]>([])
  const [weights, setWeights] = useState({ benchmark: 0.5, agents: 0.5 })
  const [region, setRegion] = useState('')
  const [sort, setSort] = useState<SortKey>('avg_final')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchRankings().then((r) => { setRows(r.rankings); setWeights(r.weights) }).catch((e) => setError(String(e)))
  }, [])

  const visible = useMemo(
    () => rows.filter((r) => !region || r.region === region).sort((a, b) => b[sort] - a[sort]),
    [rows, region, sort],
  )
  const regionAvg = useMemo(() => {
    const acc: Record<string, { sum: number; n: number }> = {}
    for (const r of rows) { (acc[r.region] ??= { sum: 0, n: 0 }).sum += r.avg_final; acc[r.region].n += 1 }
    return Object.entries(acc).map(([reg, v]) => ({ region: reg, avg: v.sum / v.n, n: v.n })).sort((a, b) => b.avg - a.avg)
  }, [rows])

  const th = (key: SortKey, label: string) => (
    <th className={`num sortable ${sort === key ? 'sorted' : ''}`} onClick={() => setSort(key)}>{label}{sort === key ? ' ▾' : ''}</th>
  )

  return (
    <div className="page">
      <div className="session-head">
        <div>
          <h2>Model rankings</h2>
          <div className="muted small">Our own evaluation: {Math.round(weights.benchmark * 100)}% open-source benchmarks + {Math.round(weights.agents * 100)}% persona-agent feedback (default weights; sessions may override). Ranked by average final score across sessions.</div>
        </div>
        <div className="head-actions">
          {['', 'CN', 'US'].map((r) => (
            <button key={r} className={`tab-button ${region === r ? 'active' : ''}`} onClick={() => setRegion(r)}>{r ? `${REGION_FLAG[r]} ${r}` : 'All'}</button>
          ))}
        </div>
      </div>
      {error && <div className="error-text">{error}</div>}

      {regionAvg.length > 1 && (
        <div className="region-strip">
          {regionAvg.map((r) => (
            <div key={r.region} className="panel region-card">
              <div className="region-flag">{REGION_FLAG[r.region] ?? '🌐'}</div>
              <div><div className="muted small">{r.region} · {r.n} model{r.n > 1 ? 's' : ''}</div><div className="region-score" style={{ color: scoreColor(r.avg) }}>{r.avg.toFixed(1)}</div></div>
            </div>
          ))}
        </div>
      )}

      <div className="panel table-panel">
        <table className="data-table rankings">
          <thead>
            <tr>
              <th>#</th><th>model</th><th>vendor</th>
              {th('avg_final', 'avg final')}{th('best_final', 'best')}{th('latest_final', 'latest')}
              {th('avg_benchmark', 'benchmarks')}{th('avg_agents', 'agents')}{th('sessions', 'runs')}
              <th>last evaluated</th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && <tr><td colSpan={10} className="muted">No completed sessions yet. <Link to="/evaluate">Evaluate a model →</Link></td></tr>}
            {visible.map((r, i) => (
              <tr key={r.model}>
                <td className="rank">{i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : i + 1}</td>
                <td><b>{REGION_FLAG[r.region] ?? ''} {r.model}</b></td>
                <td className="muted">{r.vendor}</td>
                <td className="num score-cell">
                  <div className="score-with-bar"><span style={{ color: scoreColor(r.avg_final), fontWeight: 700 }}>{fmt(r.avg_final)}</span><ScoreBar value={r.avg_final} height={6} /></div>
                </td>
                <td className="num"><Link to={`/sessions/${r.best_session_id}`}>{fmt(r.best_final)}</Link></td>
                <td className="num"><Link to={`/sessions/${r.latest_session_id}`}>{fmt(r.latest_final)}</Link></td>
                <td className="num">{fmt(r.avg_benchmark)}</td>
                <td className="num">{fmt(r.avg_agents)}</td>
                <td className="num">{r.sessions}</td>
                <td className="small muted">{new Date(r.last_evaluated).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
