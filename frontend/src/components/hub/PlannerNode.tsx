import { Handle, Position } from '@xyflow/react'
import { useHubStore } from '../../hubStore'
import HubModelSelect from '../HubModelSelect'
import StatusBadge from '../StatusBadge'

/** The Planner analyzes the brief, sizes the team, and assigns every task. */
export default function PlannerNode() {
  const phase = useHubStore((s) => s.phase)
  const status = useHubStore((s) => s.plannerStatus)
  const plan = useHubStore((s) => s.plan)
  const call = useHubStore((s) => s.plannerCall)
  const title = useHubStore((s) => s.title)
  const startRun = useHubStore((s) => s.startRun)
  const resetRun = useHubStore((s) => s.resetRun)

  const running = phase === 'planning' || phase === 'building' || phase === 'integrating'
  const concluded = phase === 'closed' || phase === 'error'

  return (
    <div className={`court-node planner-node status-${status}`}>
      <div className="node-header">
        <span className="node-icon">&#129504;</span>
        <span>Planner</span>
        <StatusBadge status={status} />
      </div>
      <p className="node-blurb">
        Analyzes the brief, decides how many agents the team needs, and assigns each task to
        exactly one agent.
      </p>
      <label className="field-label">Model</label>
      <HubModelSelect role="planner" />

      {!concluded && (
        <button
          className="nodrag run-button"
          onClick={startRun}
          disabled={running || !title.trim()}
        >
          {running ? 'Team at work…' : '🚀 Assemble team & build'}
        </button>
      )}
      {concluded && (
        <button className="nodrag close-button" onClick={resetRun}>
          &#8635; New run
        </button>
      )}

      {plan && (
        <div className="result-block">
          <div className="metrics">
            <span>team of {plan.team_size}</span>
            {call && <span>{call.latency_ms} ms</span>}
            {plan.fallback && <span className="error-text">fallback plan</span>}
          </div>
          <span className="field-label">Analysis</span>
          <p className="rationale nodrag">{plan.analysis}</p>
          <span className="field-label">Why this team</span>
          <p className="rationale nodrag">{plan.rationale}</p>
        </div>
      )}
      {call && call.status === 'error' && (
        <div className="result-block error-text">{call.error}</div>
      )}
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
    </div>
  )
}
