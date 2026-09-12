import { NavLink, Route, Routes } from 'react-router-dom'
import CourtCanvas from './components/CourtCanvas'
import HubCanvas from './components/hub/HubCanvas'
import HubTracePanel from './components/hub/HubTracePanel'
import AgentsPage from './eval/pages/AgentsPage'
import EvaluatePage from './eval/pages/EvaluatePage'
import RankingsPage from './eval/pages/RankingsPage'
import SessionPage from './eval/pages/SessionPage'
import SessionsPage from './eval/pages/SessionsPage'
import { useEvalStore } from './eval/store'
import { useHubStore } from './hubStore'
import { useCourtStore } from './store'

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

function EvalStatus() {
  const running = useEvalStore((s) => s.running)
  return (
    <span className="session-status">{running ? 'evaluation running…' : 'model evaluation'}</span>
  )
}

function CourtPage() {
  return (
    <main className="canvas-wrap">
      <CourtCanvas />
    </main>
  )
}

/** Coding Hub: same node-editor surface as the court, plus the lifecycle /
 * workspace transparency panel. */
function HubPage() {
  return (
    <main className="canvas-wrap hub-layout">
      <div className="hub-canvas">
        <HubCanvas />
      </div>
      <HubTracePanel />
    </main>
  )
}

export default function App() {
  const platform = useCourtStore((s) => s.platform)
  const running = useEvalStore((s) => s.running)
  const runs = useEvalStore((s) => s.runs)

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>
          <span className="gavel">&#9878;&#65039;</span> AI Court System
        </h1>
        <nav className="main-nav">
          <NavLink to="/" end>Court</NavLink>
          <NavLink to="/hub">Coding Hub</NavLink>
          <NavLink to="/evaluate">Evaluate {running && <span className="nav-dot" title={`${runs.length} session(s) running`} />}</NavLink>
          <NavLink to="/sessions">Sessions</NavLink>
          <NavLink to="/rankings">Rankings</NavLink>
          <NavLink to="/agents">Agents</NavLink>
        </nav>
        <div className="platform-chips" title="Inference platform serving the court">
          <span className="platform-chip platform-active">
            &#9889; {platform?.label ?? 'Canopy Wave'}
          </span>
          <span className="platform-chip platform-soon">&#129303; Hugging Face · soon</span>
          <span className="platform-chip platform-soon">&#129433; Ollama (OpenClaw) · soon</span>
        </div>
        <Routes>
          <Route path="/" element={<CourtStatus />} />
          <Route path="/hub" element={<HubStatus />} />
          <Route path="*" element={<EvalStatus />} />
        </Routes>
      </header>
      <Routes>
        <Route path="/" element={<CourtPage />} />
        <Route path="/hub" element={<HubPage />} />
        <Route path="/evaluate" element={<EvaluatePage />} />
        <Route path="/sessions" element={<SessionsPage />} />
        <Route path="/sessions/:id" element={<SessionPage />} />
        <Route path="/rankings" element={<RankingsPage />} />
        <Route path="/agents" element={<AgentsPage />} />
      </Routes>
    </div>
  )
}
