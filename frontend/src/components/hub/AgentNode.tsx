import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import { useHubStore } from '../../hubStore'
import StatusBadge from '../StatusBadge'

export type AgentNodeType = Node<{ agentId: string }, 'agent'>

/** One engineer on the team. Helpers are agents with a parent. */
export default function AgentNode({ data }: NodeProps<AgentNodeType>) {
  const agent = useHubStore((s) => s.agents[data.agentId])
  const status = useHubStore((s) => s.agentStatus[data.agentId] ?? 'idle')
  const result = useHubStore((s) => s.agentResults[data.agentId])
  const selectFile = useHubStore((s) => s.selectFile)

  if (!agent) return null
  const isHelper = agent.parent_id !== null

  return (
    <div className={`court-node agent-node status-${status} ${isHelper ? 'helper-node' : ''}`}>
      <div className="node-header">
        <span className="node-icon">{isHelper ? '\u{1F91D}' : '\u{1F468}‍\u{1F4BB}'}</span>
        <span>{agent.name}</span>
        <StatusBadge status={status} />
      </div>
      <p className="node-blurb">
        <strong>{agent.role}</strong>
        {agent.specialty && <> · {agent.specialty}</>}
        {isHelper && (
          <>
            <br />
            summoned by <code>{agent.parent_id}</code>
            {agent.summoned_reason && <> — {agent.summoned_reason}</>}
          </>
        )}
      </p>

      <span className="field-label">Tasks</span>
      <ul className="task-list nodrag">
        {agent.tasks.map((task) => (
          <li key={task.id}>
            <span className="task-title">{task.title}</span>
            {task.description && <span className="task-desc"> — {task.description}</span>}
            {task.deliverables.length > 0 && (
              <span className="task-files">{task.deliverables.join(', ')}</span>
            )}
          </li>
        ))}
      </ul>

      {result && (
        <div className="result-block">
          <div className="metrics">
            <span>{result.call.model}</span>
            <span>{result.call.latency_ms} ms</span>
            {result.call.retries_used > 0 && <span>{result.call.retries_used} retries</span>}
            {result.call.completion_tokens != null && (
              <span>{result.call.completion_tokens} tok</span>
            )}
          </div>
          {result.status === 'ok' ? (
            <>
              <p className="rationale nodrag">{result.summary || '(no summary)'}</p>
              {result.files.length > 0 && (
                <div className="file-chips nodrag">
                  {result.files.map((f) => (
                    <button
                      key={f.path}
                      className="file-chip"
                      onClick={() => selectFile(f.path)}
                      title="Open in workspace"
                    >
                      {f.path}
                    </button>
                  ))}
                </div>
              )}
              {result.help_request && (
                <p className="summon-note">
                  &#128227; asked for a <strong>{result.help_request.role}</strong>:{' '}
                  {result.help_request.task}
                  {result.helper_id ? '' : ' (denied — see lifecycle)'}
                </p>
              )}
            </>
          ) : (
            <div className="error-text">{result.call.error}</div>
          )}
        </div>
      )}
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
    </div>
  )
}
