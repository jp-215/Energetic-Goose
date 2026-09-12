import { useEffect, useMemo, useRef } from 'react'
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  useNodesState,
  type Edge,
  type Node,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useHubStore } from '../../hubStore'
import AgentNode from './AgentNode'
import BriefNode from './BriefNode'
import IntegratorNode from './IntegratorNode'
import PlannerNode from './PlannerNode'

const nodeTypes = { brief: BriefNode, planner: PlannerNode, agent: AgentNode, integrator: IntegratorNode }

const COL = { brief: 0, planner: 440, agents: 880, helpers: 1320, integrator: 1760 }
const ROW_GAP = 620

const baseNodes: Node[] = [
  { id: 'brief', type: 'brief', position: { x: COL.brief, y: 120 }, data: {} },
  { id: 'planner', type: 'planner', position: { x: COL.planner, y: 120 }, data: {} },
  { id: 'integrator', type: 'integrator', position: { x: COL.helpers, y: 190 }, data: {} },
]

/** Same node-editor surface as the court, but the team is dynamic: agent nodes
 * appear as the planner assigns them and as agents summon helpers. */
export default function HubCanvas() {
  const agentOrder = useHubStore((s) => s.agentOrder)
  const agents = useHubStore((s) => s.agents)
  const agentStatus = useHubStore((s) => s.agentStatus)
  const integratorStatus = useHubStore((s) => s.integratorStatus)
  const phase = useHubStore((s) => s.phase)

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>(baseNodes)
  const dragged = useRef(new Set<string>())

  // Sync the node list with the team: add new agents, drop agents of a reset run,
  // and keep the integrator to the right of the widest column.
  useEffect(() => {
    const topLevel = agentOrder.filter((id) => agents[id]?.parent_id === null)
    const hasHelpers = agentOrder.some((id) => agents[id]?.parent_id !== null)
    const rowOf = (id: string) => topLevel.indexOf(id)

    setNodes((current) => {
      const existing = new Map(current.map((n) => [n.id, n]))
      const next: Node[] = []

      for (const base of baseNodes) {
        const node = existing.get(base.id) ?? base
        if (base.id === 'integrator' && !dragged.current.has('integrator')) {
          const rows = Math.max(topLevel.length, 1)
          next.push({
            ...node,
            position: { x: hasHelpers ? COL.integrator : COL.helpers, y: ((rows - 1) * ROW_GAP) / 2 + 70 },
          })
        } else {
          next.push(node)
        }
      }

      for (const id of agentOrder) {
        const agent = agents[id]
        if (!agent) continue
        const found = existing.get(id)
        if (found) {
          next.push(found)
          continue
        }
        const parentRow = agent.parent_id ? rowOf(agent.parent_id) : rowOf(id)
        next.push({
          id,
          type: 'agent',
          position: {
            x: agent.parent_id ? COL.helpers : COL.agents,
            y: Math.max(parentRow, 0) * ROW_GAP + (agent.parent_id ? 60 : 0),
          },
          data: { agentId: id },
        })
      }
      return next
    })
  }, [agentOrder, agents, setNodes])

  useEffect(() => {
    if (phase === 'idle') dragged.current.clear()
  }, [phase])

  const edges: Edge[] = useMemo(() => {
    const list: Edge[] = [
      { id: 'brief-planner', source: 'brief', target: 'planner', animated: phase === 'planning' },
    ]
    for (const id of agentOrder) {
      const agent = agents[id]
      if (!agent) continue
      const working = agentStatus[id] === 'deliberating'
      if (agent.parent_id) {
        list.push({
          id: `${agent.parent_id}-${id}`,
          source: agent.parent_id,
          target: id,
          animated: working,
          label: 'summoned',
          style: { strokeDasharray: '6 4' },
        })
      } else {
        list.push({ id: `planner-${id}`, source: 'planner', target: id, animated: working })
      }
      list.push({
        id: `${id}-integrator`,
        source: id,
        target: 'integrator',
        animated: integratorStatus === 'deliberating',
      })
    }
    return list
  }, [agentOrder, agents, agentStatus, integratorStatus, phase])

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onNodeDragStop={(_, node) => dragged.current.add(node.id)}
      nodeTypes={nodeTypes}
      fitView
      minZoom={0.2}
      proOptions={{ hideAttribution: true }}
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1.5} />
      <MiniMap pannable zoomable />
      <Controls />
    </ReactFlow>
  )
}
