import { fmtDuration, fmtTokens, type Progress } from '../types'
import { ScoreBar } from './ScoreTile'

const STEPS: { key: 'benchmarks' | 'agents' | 'scoring'; label: string; hint: string }[] = [
  { key: 'benchmarks', label: '① Benchmark evaluation', hint: 'open-source benchmark items' },
  { key: 'agents', label: '② Simulated agents testing', hint: 'persona turns + feedback forms' },
  { key: 'scoring', label: '③ Scoring', hint: 'weighted final score' },
]

const ICON: Record<string, string> = { pending: '○', running: '◌', done: '●', error: '✕' }

/** Three-stage progress with overall percent, elapsed, ETA and running token spend. */
export default function ProgressStepper({ progress, compact = false }: { progress: Progress; compact?: boolean }) {
  const eta =
    progress.stage === 'done'
      ? 'finished'
      : progress.eta_s == null
        ? 'estimating…'
        : `${progress.eta_is_estimate ? '~' : ''}${fmtDuration(progress.eta_s)} left`
  const agentTok = progress.tokens_by_stage?.agents
  return (
    <div className={`stepper ${compact ? 'compact' : ''}`}>
      <div className="stepper-steps">
        {STEPS.map((s, i) => {
          const st = progress.stages[s.key]
          return (
            <div key={s.key} className={`step step-${st.status}`}>
              <div className="step-head">
                <span className="step-icon">{ICON[st.status]}</span>
                <span className="step-label">{s.label}</span>
              </div>
              <div className="step-sub muted small">
                {s.key === 'scoring'
                  ? st.status === 'done' ? 'done' : st.status === 'running' ? 'computing…' : 'waiting'
                  : `${st.done}/${st.total} ${s.hint}`}
                {st.seconds != null && <> · {fmtDuration(st.seconds)}</>}
              </div>
              {i < STEPS.length - 1 && <div className="step-arrow">→</div>}
            </div>
          )
        })}
      </div>
      <div className="stepper-bar">
        <ScoreBar value={progress.percent} color={progress.stage === 'error' ? 'var(--err)' : progress.stage === 'done' ? 'var(--ok)' : 'var(--accent-2)'} height={10} />
        <div className="stepper-meta small">
          <span><b>{progress.percent.toFixed(0)}%</b> · {progress.units_done}/{progress.units_total} model calls</span>
          <span>elapsed <b>{fmtDuration(progress.elapsed_s)}</b></span>
          <span className={progress.eta_is_estimate ? 'muted' : ''}>ETA <b>{eta}</b></span>
          <span title="prompt + completion tokens spent so far">
            tokens <b>{fmtTokens(progress.tokens?.total)}</b>
            {progress.tokens?.estimated && <span className="muted"> (est.)</span>}
            {!compact && agentTok && (
              <span className="muted"> · bench {fmtTokens(progress.tokens_by_stage.benchmarks.total)} · model {fmtTokens(agentTok.target.total)} · simulator {fmtTokens(agentTok.simulator.total)}</span>
            )}
          </span>
        </div>
      </div>
    </div>
  )
}
