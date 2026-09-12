import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import { useCourtStore } from '../../store'
import type { Role } from '../../types'
import ModelSelect from '../ModelSelect'
import StatusBadge from '../StatusBadge'
import VerdictChip from '../VerdictChip'

export type CounselNodeType = Node<{ role: Role; label: string; blurb: string }, 'counsel'>

export default function CounselNode({ data }: NodeProps<CounselNodeType>) {
  const status = useCourtStore((s) => s.roleStatus[data.role])
  const result = useCourtStore((s) => s.roleResults[data.role])

  return (
    <div className={`court-node counsel-node status-${status}`}>
      <div className="node-header">
        <span className="node-icon">&#9878;&#65039;</span>
        <span>{data.label}</span>
        <StatusBadge status={status} />
      </div>
      <p className="node-blurb">{data.blurb}</p>
      <label className="field-label">Model</label>
      <ModelSelect role={data.role} />
      {result && result.status === 'ok' && (
        <div className="result-block">
          <VerdictChip verdict={result.verdict} />
          <div className="metrics">
            <span>{result.model}</span>
            {result.confidence != null && <span>conf {Math.round(result.confidence * 100)}%</span>}
            <span>{result.latency_ms} ms</span>
            {result.retries_used > 0 && <span>{result.retries_used} retries</span>}
          </div>
          {result.rationale && <p className="rationale nodrag">{result.rationale}</p>}
        </div>
      )}
      {result && result.status === 'error' && (
        <div className="result-block error-text">{result.error}</div>
      )}
      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
    </div>
  )
}
