import { useState } from 'react'
import CourtCanvas from './components/CourtCanvas'
import HubCanvas from './components/hub/HubCanvas'
import HubTracePanel from './components/hub/HubTracePanel'
import { useHubStore } from './hubStore'
import { useCourtStore } from './store'

type Tab = 'court' | 'hub'

const COURT_PHASE_LABELS: Record<string, string> = {
  idle: 'Awaiting case',
  counsels: 'Counsels deliberating…',
  judge: 'Judge deliberating…',
  error: 'Case failed — see judge node',
}

const HUB_PHASE_LABELS: Record<string, string> = {
  idle: 'Awaiting brief',
  planning: 'Planner analyzing…',
  building: 'Agents building…',
  integrating: 'Integrator assembling…',
  error: 'Run failed — see lifecycle',
}

function CourtStatus() {
  const phase = useCourtStore((s) => s.phase)
  const result = useCourtStore((s) => s.result)
  const label =
    phase === 'closed' && result
      ? `Case ${result.case_id} closed: ${result.final_verdict}`
      : (COURT_PHASE_LABELS[phase] ?? phase)
  return <span className={`session-status session-${phase}`}>{label}</span>
}

function HubStatus() {
  const phase = useHubStore((s) => s.phase)
  const result = useHubStore((s) => s.result)
  const label =
    phase === 'closed' && result
      ? `Run ${result.run_id} complete: ${result.workspace.length} files`
      : (HUB_PHASE_LABELS[phase] ?? phase)
  return <span className={`session-status session-${phase}`}>{label}</span>
}

export default function App() {
  const [tab, setTab] = useState<Tab>('court')
  const platform = useCourtStore((s) => s.platform)

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>
          <span className="gavel">&#9878;&#65039;</span> AI Court System
        </h1>
        <nav className="app-tabs" aria-label="Workspace">
          <button className={tab === 'court' ? 'active' : ''} onClick={() => setTab('court')}>
            &#9878;&#65039; Court
          </button>
          <button className={tab === 'hub' ? 'active' : ''} onClick={() => setTab('hub')}>
            &#128736;&#65039; Coding Hub
          </button>
        </nav>
        <div className="platform-chips" title="Inference platform serving the court">
          <span className="platform-chip platform-active">
            &#9889; {platform?.label ?? 'Canopy Wave'}
          </span>
          <span className="platform-chip platform-soon">&#129303; Hugging Face · soon</span>
          <span className="platform-chip platform-soon">&#129433; Ollama (OpenClaw) · soon</span>
        </div>
        {tab === 'court' ? <CourtStatus /> : <HubStatus />}
      </header>
      {tab === 'court' ? (
        <main className="canvas-wrap">
          <CourtCanvas />
        </main>
      ) : (
        <main className="canvas-wrap hub-layout">
          <div className="hub-canvas">
            <HubCanvas />
          </div>
          <HubTracePanel />
        </main>
      )}
    </div>
  )
}
