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
  const runId = useHubStore((s) => s.runId)
  const fileCount = useHubStore((s) => Object.keys(s.workspace).length)
  const repoName = useHubStore((s) => s.repoName)
  const setRepoName = useHubStore((s) => s.setRepoName)
  const repoPrivate = useHubStore((s) => s.repoPrivate)
  const setRepoPrivate = useHubStore((s) => s.setRepoPrivate)
  const publishStatus = useHubStore((s) => s.publishStatus)
  const publishError = useHubStore((s) => s.publishError)
  const repoUrl = useHubStore((s) => s.repoUrl)
  const publishRun = useHubStore((s) => s.publishRun)

  const concluded = phase === 'closed' || phase === 'error'
  const canPush = concluded && runId !== null && fileCount > 0
  const pushing = publishStatus === 'working'
  const pushed = publishStatus === 'done'

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

      {canPush && (
        <div className="result-block push-block">
          <span className="field-label">GitHub repository</span>
          <div className="push-row">
            <input
              className="nodrag field-input"
              value={repoName}
              onChange={(e) => setRepoName(e.target.value)}
              placeholder="repo-name"
              disabled={pushing || pushed}
            />
            <label className="nodrag check-label">
              <input
                type="checkbox"
                checked={repoPrivate}
                onChange={(e) => setRepoPrivate(e.target.checked)}
                disabled={pushing || pushed}
              />
              private
            </label>
          </div>
          <button
            className="nodrag run-button push-button"
            onClick={publishRun}
            disabled={pushing || pushed || !repoName.trim()}
          >
            {pushing ? 'Pushing…' : pushed ? '✓ Pushed' : '🐙 Push Repo'}
          </button>
          {pushed && repoUrl && (
            <a className="nodrag repo-link" href={repoUrl} target="_blank" rel="noreferrer">
              {repoUrl}
            </a>
          )}
          {publishStatus === 'error' && <div className="error-text">{publishError}</div>}
          <p className="node-hint">
            Exports {fileCount} files to workspaces/, runs git init + commit, then creates and
            pushes the repo with the gh CLI.
          </p>
        </div>
      )}
      <Handle type="target" position={Position.Left} />
    </div>
  )
}
