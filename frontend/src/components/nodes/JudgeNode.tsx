import { Handle, Position } from '@xyflow/react'
import { useCourtStore } from '../../store'
import ModelSelect from '../ModelSelect'
import StatusBadge from '../StatusBadge'
import VerdictChip from '../VerdictChip'

/** The Judge is the case authority: opens the case (gavel), receives both
 * counsel opinions, rules, and closes the case. */
export default function JudgeNode() {
  const phase = useCourtStore((s) => s.phase)
  const status = useCourtStore((s) => s.roleStatus.judge)
  const judge = useCourtStore((s) => s.roleResults.judge)
  const result = useCourtStore((s) => s.result)
  const error = useCourtStore((s) => s.error)
  const title = useCourtStore((s) => s.title)
  const startCase = useCourtStore((s) => s.startCase)
  const closeCase = useCourtStore((s) => s.closeCase)

  const inSession = phase === 'counsels' || phase === 'judge'
  const concluded = phase === 'closed' || phase === 'error'

  return (
    <div className={`court-node judge-node status-${status}`}>
      <div className="node-header">
        <span className="node-icon">&#129337;&#8205;&#9878;&#65039;</span>
        <span>Judge</span>
        <StatusBadge status={status} />
      </div>
      <p className="node-blurb">
        Presides over the case: opens the session, weighs both counsel opinions, and issues the
        final ruling.
      </p>
      <label className="field-label">Model</label>
      <ModelSelect role="judge" />

      {!concluded && (
        <button
          className="nodrag run-button"
          onClick={startCase}
          disabled={inSession || !title.trim()}
        >
          {inSession ? 'Court in session…' : '⚖️ Start Case'}
        </button>
      )}
      {concluded && (
        <button className="nodrag close-button" onClick={closeCase}>
          &#128296; Close Case
        </button>
      )}

      {result && (
        <div className="result-block">
          <div className="final-verdict">
            <span className="field-label">Final verdict</span>
            <VerdictChip verdict={result.final_verdict} large />
          </div>
          <div className="metrics">
            {judge?.confidence != null && <span>conf {Math.round(judge.confidence * 100)}%</span>}
            <span>total {result.total_latency_ms} ms</span>
            {result.total_retries > 0 && <span>{result.total_retries} retries</span>}
          </div>
          {result.judge_rationale && <p className="rationale nodrag">{result.judge_rationale}</p>}
        </div>
      )}
      {phase === 'error' && error && <div className="result-block error-text">{error}</div>}
      <Handle type="target" position={Position.Left} />
    </div>
  )
}
