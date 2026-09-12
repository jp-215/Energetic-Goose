import CourtCanvas from './components/CourtCanvas'
import { useCourtStore } from './store'

const PHASE_LABELS: Record<string, string> = {
  idle: 'Awaiting case',
  counsels: 'Counsels deliberating…',
  judge: 'Judge deliberating…',
  error: 'Case failed — see judge node',
}

export default function App() {
  const phase = useCourtStore((s) => s.phase)
  const result = useCourtStore((s) => s.result)
  const platform = useCourtStore((s) => s.platform)

  const statusLabel =
    phase === 'closed' && result
      ? `Case ${result.case_id} closed: ${result.final_verdict}`
      : (PHASE_LABELS[phase] ?? phase)

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>
          <span className="gavel">&#9878;&#65039;</span> AI Court System
        </h1>
        <div className="platform-chips" title="Inference platform serving the court">
          <span className="platform-chip platform-active">
            &#9889; {platform?.label ?? 'Canopy Wave'}
          </span>
          <span className="platform-chip platform-soon">&#129303; Hugging Face · soon</span>
          <span className="platform-chip platform-soon">&#129433; Ollama (OpenClaw) · soon</span>
        </div>
        <span className={`session-status session-${phase}`}>{statusLabel}</span>
      </header>
      <main className="canvas-wrap">
        <CourtCanvas />
      </main>
    </div>
  )
}
