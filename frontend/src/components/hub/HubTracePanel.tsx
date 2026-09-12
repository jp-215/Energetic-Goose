import { useState } from 'react'
import { useHubStore } from '../../hubStore'
import type { CallTrace, TraceEntry } from '../../types'

type PanelTab = 'lifecycle' | 'workspace'

const PHASE_LABELS: Record<string, string> = {
  idle: 'Awaiting brief',
  planning: 'Planner analyzing…',
  building: 'Agents building…',
  integrating: 'Integrator assembling…',
  closed: 'Run complete',
  error: 'Run failed',
}

function ms(value: number) {
  return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${value}ms`
}

/** Every model call is auditable: model, latency, tokens, and the exact prompts. */
function CallDetails({ call }: { call: CallTrace }) {
  return (
    <details className="call-details">
      <summary>
        <span className="mono">{call.model}</span> · {ms(call.latency_ms)}
        {call.retries_used > 0 && <> · {call.retries_used} retries</>}
        {call.prompt_tokens != null && (
          <>
            {' '}
            · {call.prompt_tokens}→{call.completion_tokens ?? '?'} tok
          </>
        )}
        {call.finish_reason === 'length' && (
          <span className="warn-text"> · ⚠ output cut off at max_tokens</span>
        )}
        {call.status === 'error' && <span className="error-text"> · {call.error}</span>}
      </summary>
      <details>
        <summary>System prompt</summary>
        <pre>{call.system_prompt}</pre>
      </details>
      <details>
        <summary>User prompt</summary>
        <pre>{call.user_prompt}</pre>
      </details>
      <details>
        <summary>Raw model output</summary>
        <pre>{call.raw_output || '(empty)'}</pre>
      </details>
    </details>
  )
}

function TraceRow({ entry }: { entry: TraceEntry }) {
  const agents = useHubStore((s) => s.agents)
  const nameOf = (id: string) => agents[id]?.name ?? id

  let icon = '•'
  let title: React.ReactNode = entry.event
  let body: React.ReactNode = null
  let tone = ''

  switch (entry.event) {
    case 'run_accepted':
      icon = '▶'
      title = (
        <>
          Run <span className="mono">{entry.run_id}</span> accepted · max team {entry.max_agents}
        </>
      )
      body = (
        <div className="trace-kv">
          {Object.entries(entry.models).map(([role, model]) => (
            <span key={role}>
              {role}: <span className="mono">{model}</span>
            </span>
          ))}
        </div>
      )
      break
    case 'planner_started':
      icon = '🧠'
      title = (
        <>
          Planner (<span className="mono">{entry.model}</span>) analyzing the brief
        </>
      )
      break
    case 'plan_ready':
      icon = '🗺'
      tone = entry.plan.fallback ? 'warn' : ''
      title = <>Plan ready: team of {entry.plan.team_size}{entry.plan.fallback ? ' (fallback)' : ''}</>
      body = (
        <>
          <p>{entry.plan.analysis}</p>
          <p className="muted">{entry.plan.rationale}</p>
          <ul className="assign-list">
            {entry.plan.agents.map((a) => (
              <li key={a.id}>
                <strong>{a.name}</strong> — {a.role}
                <ul>
                  {a.tasks.map((t) => (
                    <li key={t.id}>
                      {t.title}
                      {t.deliverables.length > 0 && (
                        <span className="mono muted"> → {t.deliverables.join(', ')}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
          {entry.plan.integration_notes && (
            <p className="muted">Integration: {entry.plan.integration_notes}</p>
          )}
          <CallDetails call={entry.call} />
        </>
      )
      break
    case 'team_assembled':
      icon = '👥'
      title = <>Team assembled: {entry.agent_ids.map(nameOf).join(', ')}</>
      break
    case 'agent_started':
      icon = '⚙'
      title = (
        <>
          {entry.agent.name} ({entry.agent.role}) started on{' '}
          <span className="mono">{entry.model}</span>
        </>
      )
      body = (
        <ul>
          {entry.agent.tasks.map((t) => (
            <li key={t.id}>{t.title}</li>
          ))}
        </ul>
      )
      break
    case 'agent_summoned':
      icon = '📣'
      tone = 'accent'
      title = (
        <>
          {nameOf(entry.parent_id)} summoned <strong>{entry.agent.name}</strong> ({entry.agent.role})
        </>
      )
      body = (
        <>
          <p>{entry.request.task}</p>
          {entry.request.reason && <p className="muted">Reason: {entry.request.reason}</p>}
        </>
      )
      break
    case 'summon_denied':
      icon = '⛔'
      tone = 'warn'
      title = <>Summon denied for {nameOf(entry.agent_id)}: {entry.reason}</>
      body = <p className="muted">Requested a {entry.request.role}: {entry.request.task}</p>
      break
    case 'agent_result':
      icon = entry.result.status === 'ok' ? '✅' : '❌'
      tone = entry.result.status === 'ok' ? 'ok' : 'err'
      title = (
        <>
          {nameOf(entry.agent_id)} finished · {entry.result.files.length} file
          {entry.result.files.length === 1 ? '' : 's'}
        </>
      )
      body = (
        <>
          {entry.result.summary && <p>{entry.result.summary}</p>}
          {entry.result.notes && <p className="muted">Notes: {entry.result.notes}</p>}
          {entry.result.files.length > 0 && (
            <p className="mono muted">{entry.result.files.map((f) => f.path).join(', ')}</p>
          )}
          <CallDetails call={entry.result.call} />
        </>
      )
      break
    case 'file_conflict':
      icon = '⚠'
      tone = 'warn'
      title = (
        <>
          <span className="mono">{entry.path}</span> written by both {nameOf(entry.previous_author)} and{' '}
          {nameOf(entry.new_author)} — {entry.resolution}
        </>
      )
      break
    case 'file_rejected':
      icon = '🚫'
      tone = 'warn'
      title = (
        <>
          Rejected <span className="mono">{entry.path}</span> from {nameOf(entry.agent_id)}: {entry.reason}
        </>
      )
      break
    case 'output_truncated':
      icon = '✂'
      tone = 'warn'
      title = (
        <>
          {nameOf(entry.agent_id)} ran out of output budget ({entry.max_tokens} tokens) — any
          unfinished file is discarded, not written
        </>
      )
      break
    case 'integration_started':
      icon = '📦'
      title = (
        <>
          Integrator (<span className="mono">{entry.model}</span>) assembling {entry.file_count} files
        </>
      )
      break
    case 'integration_result':
      icon = entry.result.status === 'ok' ? '✅' : '❌'
      tone = entry.result.status === 'ok' ? 'ok' : 'err'
      title = <>Integration {entry.result.status === 'ok' ? 'complete' : 'failed'}</>
      body = (
        <>
          {entry.result.summary && <p>{entry.result.summary}</p>}
          {entry.result.run_instructions && <pre className="run-steps">{entry.result.run_instructions}</pre>}
          <CallDetails call={entry.result.call} />
        </>
      )
      break
    case 'run_closed':
      icon = entry.response.status === 'ok' ? '🏁' : '❌'
      tone = entry.response.status === 'ok' ? 'ok' : 'err'
      title = (
        <>
          Run closed: {entry.response.status} · {entry.response.workspace.length} files ·{' '}
          {entry.response.total_calls} calls · {ms(entry.response.total_latency_ms)}
        </>
      )
      body = entry.response.error ? <p className="error-text">{entry.response.error}</p> : null
      break
    case 'error':
      icon = '❌'
      tone = 'err'
      title = <>Error: {entry.detail}</>
      break
  }

  return (
    <li className={`trace-row tone-${tone || 'plain'}`}>
      <span className="trace-time">{ms(entry.at_ms)}</span>
      <span className="trace-icon">{icon}</span>
      <div className="trace-body">
        <div className="trace-title">{title}</div>
        {body && <div className="trace-detail">{body}</div>}
      </div>
    </li>
  )
}

function LifecycleTab() {
  const trace = useHubStore((s) => s.trace)
  if (trace.length === 0) {
    return (
      <div className="panel-empty">
        <p>Every step of the run lands here as it happens:</p>
        <ol>
          <li>Planner reads the brief and sizes the team</li>
          <li>Each agent's tasks, model, prompt, and raw output</li>
          <li>Helpers summoned (or denied) and why</li>
          <li>Integrator's fixes and how to run the result</li>
        </ol>
      </div>
    )
  }
  return (
    <ul className="trace-list">
      {trace.map((entry) => (
        <TraceRow key={entry.seq} entry={entry} />
      ))}
    </ul>
  )
}

function WorkspaceTab() {
  const workspace = useHubStore((s) => s.workspace)
  const selectedFile = useHubStore((s) => s.selectedFile)
  const selectFile = useHubStore((s) => s.selectFile)
  const phase = useHubStore((s) => s.phase)
  const runId = useHubStore((s) => s.runId)
  const exportStatus = useHubStore((s) => s.exportStatus)
  const exportPath = useHubStore((s) => s.exportPath)
  const exportError = useHubStore((s) => s.exportError)
  const exportRun = useHubStore((s) => s.exportRun)
  const repoName = useHubStore((s) => s.repoName)
  const setRepoName = useHubStore((s) => s.setRepoName)
  const repoPrivate = useHubStore((s) => s.repoPrivate)
  const setRepoPrivate = useHubStore((s) => s.setRepoPrivate)
  const publishStatus = useHubStore((s) => s.publishStatus)
  const repoUrl = useHubStore((s) => s.repoUrl)
  const publishError = useHubStore((s) => s.publishError)
  const publishRun = useHubStore((s) => s.publishRun)

  const paths = Object.keys(workspace).sort()
  const file = selectedFile ? workspace[selectedFile] : null
  const concluded = phase === 'closed' || phase === 'error'
  const canShip = concluded && runId !== null && paths.length > 0

  if (paths.length === 0) {
    return (
      <div className="panel-empty">
        <p>Files appear here as agents produce them. When the run closes you can export the
          workspace to disk or publish it straight to GitHub.</p>
      </div>
    )
  }

  return (
    <div className="workspace">
      <div className="workspace-files">
        {paths.map((path) => (
          <button
            key={path}
            className={`file-row ${path === selectedFile ? 'active' : ''}`}
            onClick={() => selectFile(path)}
            title={`by ${workspace[path].author}`}
          >
            <span className="mono">{path}</span>
            <span className="file-author">{workspace[path].author}</span>
          </button>
        ))}
      </div>
      <div className="workspace-view">
        {file ? (
          <>
            <div className="workspace-view-head">
              <span className="mono">{file.path}</span>
              <span className="muted">by {file.author} · {file.content.length} chars</span>
            </div>
            <pre className="file-content">{file.content}</pre>
          </>
        ) : (
          <div className="panel-empty">Select a file</div>
        )}
      </div>
      <div className="ship-bar">
        <div className="ship-row">
          <button className="ship-button" onClick={exportRun} disabled={!canShip || exportStatus === 'working'}>
            {exportStatus === 'working' ? 'Exporting…' : '💾 Export to workspaces/'}
          </button>
          {exportStatus === 'done' && exportPath && (
            <span className="mono muted ship-note" title={exportPath}>{exportPath}</span>
          )}
          {exportStatus === 'error' && <span className="error-text ship-note">{exportError}</span>}
        </div>
        <div className="ship-row">
          <input
            className="field-input repo-input"
            value={repoName}
            onChange={(e) => setRepoName(e.target.value)}
            placeholder="github-repo-name"
            disabled={publishStatus === 'working' || publishStatus === 'done'}
          />
          <label className="check-label">
            <input
              type="checkbox"
              checked={repoPrivate}
              onChange={(e) => setRepoPrivate(e.target.checked)}
              disabled={publishStatus === 'working' || publishStatus === 'done'}
            />
            private
          </label>
          <button
            className="ship-button primary"
            onClick={publishRun}
            disabled={!canShip || !repoName.trim() || publishStatus === 'working' || publishStatus === 'done'}
          >
            {publishStatus === 'working' ? 'Publishing…' : publishStatus === 'done' ? 'Published' : '🐙 Publish to GitHub'}
          </button>
        </div>
        {publishStatus === 'done' && repoUrl && (
          <div className="ship-row">
            <a className="repo-link" href={repoUrl} target="_blank" rel="noreferrer">
              {repoUrl}
            </a>
          </div>
        )}
        {publishStatus === 'error' && (
          <div className="ship-row error-text">{publishError}</div>
        )}
      </div>
    </div>
  )
}

/** Right-hand transparency panel: the full lifecycle trace and the workspace. */
export default function HubTracePanel() {
  const [tab, setTab] = useState<PanelTab>('lifecycle')
  const phase = useHubStore((s) => s.phase)
  const trace = useHubStore((s) => s.trace)
  const fileCount = useHubStore((s) => Object.keys(s.workspace).length)

  return (
    <aside className="trace-panel">
      <div className="panel-tabs">
        <button className={tab === 'lifecycle' ? 'active' : ''} onClick={() => setTab('lifecycle')}>
          Lifecycle {trace.length > 0 && <span className="count">{trace.length}</span>}
        </button>
        <button className={tab === 'workspace' ? 'active' : ''} onClick={() => setTab('workspace')}>
          Workspace {fileCount > 0 && <span className="count">{fileCount}</span>}
        </button>
        <span className={`panel-phase phase-${phase}`}>{PHASE_LABELS[phase] ?? phase}</span>
      </div>
      <div className="panel-body">{tab === 'lifecycle' ? <LifecycleTab /> : <WorkspaceTab />}</div>
    </aside>
  )
}
