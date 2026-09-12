import { Handle, Position } from '@xyflow/react'
import { useHubStore } from '../../hubStore'
import HubModelSelect from '../HubModelSelect'
import StatusBadge from '../StatusBadge'

/** The Integrator receives every agent's files and makes the project runnable. */
export default function IntegratorNode() {
  const status = useHubStore((s) => s.integratorStatus)
  const integration = useHubStore((s) => s.integration)
  const result = useHubStore((s) => s.result)
  const error = useHubStore((s) => s.error)
  const phase = useHubStore((s) => s.phase)

  return (
    <div className={`court-node integrator-node status-${status}`}>
      <div className="node-header">
        <span className="node-icon">&#128230;</span>
        <span>Integrator</span>
        <StatusBadge status={status} />
      </div>
      <p className="node-blurb">
        Collects every file the team produced, fills the gaps (README, entrypoint,
        dependencies), and hands back a runnable workspace.
      </p>
      <label className="field-label">Model</label>
      <HubModelSelect role="integrator" />

      {integration && (
        <div className="result-block">
          <div className="metrics">
            <span>{integration.call.model}</span>
            <span>{integration.call.latency_ms} ms</span>
            {result && <span>total {result.total_latency_ms} ms</span>}
            {result && <span>{result.total_calls} calls</span>}
          </div>
          {integration.status === 'ok' ? (
            <>
              <p className="rationale nodrag">{integration.summary}</p>
              {integration.run_instructions && (
                <>
                  <span className="field-label">How to run</span>
                  <pre className="run-steps nodrag">{integration.run_instructions}</pre>
                </>
              )}
            </>
          ) : (
            <div className="error-text">{integration.call.error}</div>
          )}
        </div>
      )}
      {phase === 'error' && error && <div className="result-block error-text">{error}</div>}
      <Handle type="target" position={Position.Left} />
    </div>
  )
}
