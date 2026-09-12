import { Handle, Position } from '@xyflow/react'
import { useHubStore } from '../../hubStore'

/** Project intake: the brief the planner analyzes. */
export default function BriefNode() {
  const title = useHubStore((s) => s.title)
  const context = useHubStore((s) => s.context)
  const goal = useHubStore((s) => s.goal)
  const maxAgents = useHubStore((s) => s.maxAgents)
  const phase = useHubStore((s) => s.phase)
  const setField = useHubStore((s) => s.setField)
  const setMaxAgents = useHubStore((s) => s.setMaxAgents)

  const locked = phase === 'planning' || phase === 'building' || phase === 'integrating'

  return (
    <div className="court-node brief-node">
      <div className="node-header">
        <span className="node-icon">&#128203;</span>
        <span>Project Brief</span>
      </div>
      <label className="field-label">Title</label>
      <input
        className="nodrag field-input"
        value={title}
        disabled={locked}
        onChange={(e) => setField('title', e.target.value)}
        placeholder="Project title"
      />
      <label className="field-label">Context</label>
      <textarea
        className="nodrag field-input"
        rows={6}
        value={context}
        disabled={locked}
        onChange={(e) => setField('context', e.target.value)}
        placeholder="What is this project? Constraints, stack, existing code…"
      />
      <label className="field-label">Goal / deliverable</label>
      <textarea
        className="nodrag field-input"
        rows={3}
        value={goal}
        disabled={locked}
        onChange={(e) => setField('goal', e.target.value)}
        placeholder="What must the team hand back?"
      />
      <label className="field-label">Max team size: {maxAgents}</label>
      <input
        className="nodrag range-input"
        type="range"
        min={1}
        max={5}
        value={maxAgents}
        disabled={locked}
        onChange={(e) => setMaxAgents(Number(e.target.value))}
      />
      <p className="node-hint">
        {locked ? 'The team is at work.' : 'The Planner reads this brief and assembles the team.'}
      </p>
      <Handle type="source" position={Position.Right} />
    </div>
  )
}
