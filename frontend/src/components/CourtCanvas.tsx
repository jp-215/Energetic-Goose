import { useMemo } from 'react'
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useCourtStore } from '../store'
import CaseNode from './nodes/CaseNode'
import CounselNode from './nodes/CounselNode'
import JudgeNode from './nodes/JudgeNode'

const nodeTypes = { case: CaseNode, counsel: CounselNode, judge: JudgeNode }

const initialNodes: Node[] = [
  { id: 'case', type: 'case', position: { x: 0, y: 120 }, data: {} },
  {
    id: 'simple',
    type: 'counsel',
    position: { x: 480, y: 0 },
    data: {
      role: 'simple',
      label: 'Simple Counsel',
      blurb: 'Fast, direct read of the case — the obvious facts, plainly argued.',
    },
  },
  {
    id: 'complex',
    type: 'counsel',
    position: { x: 480, y: 420 },
    data: {
      role: 'complex',
      label: 'Complex Counsel',
      blurb: 'Deep analysis — precedent, counterarguments, edge cases.',
    },
  },
  { id: 'judge', type: 'judge', position: { x: 980, y: 190 }, data: {} },
]

export default function CourtCanvas() {
  const phase = useCourtStore((s) => s.phase)
  const counselsActive = phase === 'counsels'
  const judgeActive = phase === 'judge'

  const edges: Edge[] = useMemo(
    () => [
      { id: 'case-simple', source: 'case', target: 'simple', animated: counselsActive },
      { id: 'case-complex', source: 'case', target: 'complex', animated: counselsActive },
      { id: 'simple-judge', source: 'simple', target: 'judge', animated: judgeActive },
      { id: 'complex-judge', source: 'complex', target: 'judge', animated: judgeActive },
    ],
    [counselsActive, judgeActive],
  )

  return (
    <ReactFlow
      defaultNodes={initialNodes}
      edges={edges}
      nodeTypes={nodeTypes}
      fitView
      minZoom={0.3}
      proOptions={{ hideAttribution: true }}
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1.5} />
      <MiniMap pannable zoomable />
      <Controls />
    </ReactFlow>
  )
}
