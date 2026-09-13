import { useEffect, useMemo, useState } from 'react'
import { Background, Controls, MiniMap, ReactFlow, type Edge, type Node } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { GraphNode, GraphRelationship, GraphResponse } from '../types'

/** Colours per Neo4j label (also used by the legend). */
export const LABEL_COLORS: Record<string, string> = {
  Model: '#d4a24c',
  Session: '#7aa2f7',
  Agent: '#3fb950',
  Feedback: '#f778ba',
  Benchmark: '#d29922',
  Turn: '#8b98a9',
  Paper: '#a371f7',
  KnowledgeNode: '#39c5cf',
}

function title(n: GraphNode): string {
  const p = n.properties as Record<string, string | number | undefined>
  switch (n.label) {
    case 'Model':
      return String(p.name ?? '')
    case 'Session':
      return `session ${p.id ?? ''}`.slice(0, 22)
    case 'Agent':
      return `${p.avatar ?? ''} ${p.name ?? p.id}`
    case 'Feedback':
      return `feedback ${p.score != null ? `${p.score}/100` : ''}`
    case 'Benchmark':
      return String(p.display_name ?? p.name ?? '')
    case 'Turn':
      return `#${p.index} ${p.role === 'user' ? 'asks' : 'replies'}`
    case 'Paper':
      return String(p.title ?? p.sourceId ?? '')
    case 'KnowledgeNode':
      return String(p.label ?? p.nodeId ?? '')
    default:
      return n.label
  }
}

/**
 * Radial "spoke" layout: the model under test sits at the centre, each
 * persona agent gets a spoke; the turns of its conversation run along the
 * spoke from the model outwards, the agent sits at the end of the spoke, and
 * its feedback just beyond. The session and the benchmarks it ran hang above.
 */
function layoutSession(nodes: GraphNode[], rels: GraphRelationship[]): { nodes: Node[]; edges: Edge[] } {
  const agents = nodes.filter((n) => n.label === 'Agent')
  const benchmarks = nodes.filter((n) => n.label === 'Benchmark')
  const turnsByAgent = new Map<string, GraphNode[]>()
  for (const n of nodes.filter((n) => n.label === 'Turn')) {
    const agentId = String(n.properties.agent_id ?? '')
    turnsByAgent.set(agentId, [...(turnsByAgent.get(agentId) ?? []), n])
  }
  const spokeCount = Math.max(agents.length, 1)
  // Screen angles: -PI/2 is straight up. Leave the top arc free for the
  // session + benchmarks and spread the agent spokes clockwise around the rest.
  const gap = Math.PI * 0.32
  const span = Math.PI * 2 - gap * 2
  const agentAngle = new Map<string, number>()
  agents.forEach((a, i) => {
    const t = spokeCount === 1 ? 0.5 : i / (spokeCount - 1)
    agentAngle.set(String(a.properties.id), -Math.PI / 2 + gap + span * t)
  })
  const maxTurns = Math.max(1, ...[...turnsByAgent.values()].map((t) => t.length))
  const innerR = 150
  const turnStep = 56
  const agentR = innerR + turnStep * (maxTurns + 1)
  const feedbackR = agentR + 120

  const pos = new Map<string, { x: number; y: number }>()
  const polar = (r: number, ang: number) => ({ x: r * Math.cos(ang), y: r * Math.sin(ang) })

  for (const n of nodes) {
    const p = n.properties
    switch (n.label) {
      case 'Model':
        pos.set(n.id, { x: 0, y: 0 })
        break
      case 'Session':
        pos.set(n.id, { x: 0, y: -240 })
        break
      case 'Benchmark': {
        const i = benchmarks.indexOf(n)
        const k = benchmarks.length
        const x = (i - (k - 1) / 2) * 175
        pos.set(n.id, { x, y: -460 })
        break
      }
      case 'Agent':
        pos.set(n.id, polar(agentR, agentAngle.get(String(p.id)) ?? Math.PI / 2))
        break
      case 'Feedback':
        pos.set(n.id, polar(feedbackR, agentAngle.get(String(p.agent_id)) ?? Math.PI / 2))
        break
      case 'Turn': {
        const list = (turnsByAgent.get(String(p.agent_id)) ?? []).sort(
          (a, b) => Number(a.properties.index) - Number(b.properties.index),
        )
        const i = list.indexOf(n)
        const ang = agentAngle.get(String(p.agent_id)) ?? Math.PI / 2
        const base = polar(innerR + turnStep * (i + 1), ang)
        // alternate user/assistant slightly off the spoke so the chain reads as a dialogue
        const side = p.role === 'user' ? 1 : -1
        pos.set(n.id, { x: base.x + side * 26 * Math.sin(ang), y: base.y - side * 26 * Math.cos(ang) })
        break
      }
      default:
        pos.set(n.id, { x: (Math.random() - 0.5) * 400, y: 300 })
    }
  }

  const rfNodes: Node[] = nodes.map((n) => ({
    id: n.id,
    position: pos.get(n.id) ?? { x: 0, y: 0 },
    data: { label: title(n), raw: n },
    className: `graph-node graph-node-${n.label.toLowerCase()}`,
    style: { borderColor: LABEL_COLORS[n.label] ?? 'var(--border)' },
  }))
  const rfEdges: Edge[] = rels.map((r) => ({
    id: r.id,
    source: r.from,
    target: r.to,
    label: r.type === 'IN_SESSION' ? undefined : r.type,
    className: `graph-edge graph-edge-${r.type.toLowerCase()}`,
    animated: r.type === 'INTERACTED_WITH',
    style: { opacity: r.type === 'IN_SESSION' ? 0.15 : 0.7 },
    labelStyle: { fill: 'var(--muted)', fontSize: 9 },
    labelBgStyle: { fill: 'var(--bg)', fillOpacity: 0.85 },
  }))
  return { nodes: rfNodes, edges: rfEdges }
}

/**
 * Clustered layout for the papers corpus: each knowledge node sits on an
 * outer ring and the papers that BELONGS_TO it orbit it as a topic
 * constellation; SUPPORTS / SHARES_AUTHOR edges run between the clusters.
 */
function layoutPapers(nodes: GraphNode[], rels: GraphRelationship[]): { nodes: Node[]; edges: Edge[] } {
  const pos = new Map<string, { x: number; y: number }>()
  const kns = nodes.filter((n) => n.label === 'KnowledgeNode')
  const papers = nodes.filter((n) => n.label === 'Paper')

  const ringR = 480
  kns.forEach((kn, i) => {
    const ang = (i / Math.max(kns.length, 1)) * 2 * Math.PI - Math.PI / 2
    pos.set(kn.id, { x: ringR * Math.cos(ang), y: ringR * Math.sin(ang) })
  })

  const papersByKn = new Map<string, GraphNode[]>()
  const orphans: GraphNode[] = []
  for (const p of papers) {
    const knId = rels.find((r) => r.type === 'BELONGS_TO' && r.from === p.id)?.to
    if (knId && pos.has(knId)) papersByKn.set(knId, [...(papersByKn.get(knId) ?? []), p])
    else orphans.push(p)
  }
  for (const [knId, list] of papersByKn) {
    const c = pos.get(knId)!
    const r = Math.max(150, (list.length * 80) / (2 * Math.PI))
    list.forEach((p, i) => {
      const ang = (i / list.length) * 2 * Math.PI
      pos.set(p.id, { x: c.x + r * Math.cos(ang), y: c.y + r * Math.sin(ang) })
    })
  }
  orphans.forEach((p, i) => {
    const ang = (i / Math.max(orphans.length, 1)) * 2 * Math.PI + Math.PI / 7
    pos.set(p.id, { x: (ringR + 260) * Math.cos(ang), y: (ringR + 260) * Math.sin(ang) })
  })

  const rfNodes: Node[] = nodes.map((n) => ({
    id: n.id,
    position: pos.get(n.id) ?? { x: 0, y: 0 },
    data: { label: title(n), raw: n },
    className: `graph-node graph-node-${n.label.toLowerCase()}`,
    style: { borderColor: LABEL_COLORS[n.label] ?? 'var(--border)' },
  }))
  const rfEdges: Edge[] = rels.map((r) => ({
    id: r.id,
    source: r.from,
    target: r.to,
    label: r.type === 'BELONGS_TO' ? undefined : r.type,
    className: `graph-edge graph-edge-${r.type.toLowerCase()}`,
    animated: r.type === 'SUPPORTS',
    style: { opacity: r.type === 'BELONGS_TO' ? 0.3 : 0.75 },
    labelStyle: { fill: 'var(--muted)', fontSize: 9 },
    labelBgStyle: { fill: 'var(--bg)', fillOpacity: 0.85 },
  }))
  return { nodes: rfNodes, edges: rfEdges }
}

export default function GraphView({ graph }: { graph: GraphResponse }) {
  const isPapers = graph.nodes.some((n) => n.label === 'Paper' || n.label === 'KnowledgeNode')
  const { nodes, edges } = useMemo(
    () => (isPapers ? layoutPapers(graph.nodes, graph.relationships) : layoutSession(graph.nodes, graph.relationships)),
    [graph, isPapers],
  )
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [hideSessionEdges, setHideSessionEdges] = useState(true)
  useEffect(() => setSelected(null), [graph])

  const visibleEdges = hideSessionEdges ? edges.filter((e) => !e.className?.includes('in_session')) : edges
  const counts = graph.nodes.reduce<Record<string, number>>((acc, n) => ((acc[n.label] = (acc[n.label] ?? 0) + 1), acc), {})

  return (
    <div className="graph-wrap">
      <div className="graph-toolbar">
        <div className="graph-legend">
          {Object.entries(LABEL_COLORS).filter(([label]) => counts[label] != null).map(([label, color]) => (
            <span key={label} className="legend-item">
              <span className="legend-dot" style={{ background: color }} /> {label}
              <span className="muted"> ×{counts[label]}</span>
            </span>
          ))}
        </div>
        {!isPapers && (
          <label className="check small">
            <input type="checkbox" checked={hideSessionEdges} onChange={(e) => setHideSessionEdges(e.target.checked)} />
            hide IN_SESSION edges
          </label>
        )}
      </div>
      <div className="graph-canvas">
        <ReactFlow
          nodes={nodes}
          edges={visibleEdges}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          minZoom={0.1}
          nodesDraggable
          nodesConnectable={false}
          onNodeClick={(_, node) => setSelected((node.data as { raw: GraphNode }).raw)}
          onPaneClick={() => setSelected(null)}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={24} color="#1c2330" />
          <MiniMap pannable zoomable maskColor="rgba(13,17,23,0.75)" bgColor="#161b22" nodeColor={(n) => LABEL_COLORS[(n.data as { raw: GraphNode }).raw.label] ?? '#888'} />
          <Controls />
        </ReactFlow>
        {selected && (
          <aside className="graph-inspector">
            <div className="inspector-head">
              <span className="legend-dot" style={{ background: LABEL_COLORS[selected.label] }} />
              <strong>(:{selected.label})</strong>
              <button className="link-button" onClick={() => setSelected(null)}>✕</button>
            </div>
            <dl>
              {Object.entries(selected.properties).map(([k, v]) => (
                <div key={k} className="prop-row">
                  <dt>{k}</dt>
                  <dd>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</dd>
                </div>
              ))}
            </dl>
          </aside>
        )}
      </div>
    </div>
  )
}
