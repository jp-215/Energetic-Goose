import { Handle, Position } from '@xyflow/react'
import { useCourtStore } from '../../store'

/** Case intake: holds the facts and the question. The Judge — not this
 * node — opens and closes the case. */
export default function CaseNode() {
  const title = useCourtStore((s) => s.title)
  const context = useCourtStore((s) => s.context)
  const query = useCourtStore((s) => s.query)
  const phase = useCourtStore((s) => s.phase)
  const setField = useCourtStore((s) => s.setField)

  const locked = phase === 'counsels' || phase === 'judge'

  return (
    <div className="court-node case-node">
      <div className="node-header">
        <span className="node-icon">&#128196;</span>
        <span>Case Intake</span>
      </div>
      <label className="field-label">Title</label>
      <input
        className="nodrag field-input"
        value={title}
        disabled={locked}
        onChange={(e) => setField('title', e.target.value)}
        placeholder="Case title"
      />
      <label className="field-label">Context / Facts</label>
      <textarea
        className="nodrag field-input"
        rows={6}
        value={context}
        disabled={locked}
        onChange={(e) => setField('context', e.target.value)}
        placeholder="What happened?"
      />
      <label className="field-label">Query</label>
      <textarea
        className="nodrag field-input"
        rows={3}
        value={query}
        disabled={locked}
        onChange={(e) => setField('query', e.target.value)}
        placeholder="The question before the court"
      />
      <p className="node-hint">
        {locked ? 'Case is before the court.' : 'The Judge opens and closes the case.'}
      </p>
      <Handle type="source" position={Position.Right} />
    </div>
  )
}
