import { DIMENSIONS, type AgentResult, type Persona } from '../types'
import { ScoreBar, fmt, scoreColor } from './ScoreTile'
import RatingsRadar from './RatingsRadar'

/** Full personality sheet for one simulated user, optionally with the
 * feedback it gave in a session. */
export default function PersonaModal({
  persona,
  result,
  selected,
  onToggle,
  onClose,
}: {
  persona: Persona
  result?: AgentResult | null
  selected?: boolean
  onToggle?: () => void
  onClose: () => void
}) {
  const Meter = ({ label, value }: { label: string; value: number }) => (
    <div className="meter">
      <span className="meter-label">{label}</span>
      <div className="meter-dots">{Array.from({ length: 10 }, (_, i) => <span key={i} className={i < value ? 'on' : ''} />)}</div>
      <span className="meter-val">{value}/10</span>
    </div>
  )
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal panel persona-sheet" onClick={(e) => e.stopPropagation()}>
        <button className="link-button modal-close" onClick={onClose}>✕</button>
        <div className="sheet-head">
          <div className="avatar-circle static" style={{ width: 88, height: 88, fontSize: 44 }}>{persona.avatar}</div>
          <div className="grow">
            <h3>{persona.name} {persona.builtin && <span className="pill">built-in</span>}</h3>
            <div className="muted">{persona.tagline}</div>
            <div className="muted small">
              {persona.age ? `${persona.age} · ` : ''}{persona.occupation} · {persona.expertise_level} · writes in <b>{persona.language}</b>
            </div>
            <div className="chips small-chips">{persona.personality_traits.map((t) => <span key={t} className="chip">{t}</span>)}</div>
          </div>
          {result && (
            <div className="sheet-score" style={{ color: scoreColor(result.score) }}>
              {fmt(result.score)}<span className="muted small">/100</span>
              <div className="muted small">their score</div>
            </div>
          )}
        </div>

        <div className="sheet-grid">
          <section>
            <h4>Who they are</h4>
            <p>{persona.background}</p>
            <h4>How they talk</h4>
            <p>{persona.communication_style}</p>
            <Meter label="patience" value={persona.patience} />
            <Meter label="strictness" value={persona.strictness} />
          </section>
          <section>
            <h4>What they care about</h4>
            <div className="ratings-bars compact">
              {DIMENSIONS.map((d) => (
                <div key={d} className="rating-row">
                  <span className="rating-name">{d}</span>
                  <ScoreBar value={(persona.priorities[d] ?? 0) * 100} height={6} color="var(--accent-2)" />
                  <span className="rating-val">{Math.round((persona.priorities[d] ?? 0) * 100)}%</span>
                </div>
              ))}
            </div>
            <h4>Scenario · {persona.scenario.title}</h4>
            <p className="muted small">{persona.scenario.goal}</p>
            <blockquote>“{persona.scenario.opening_message}”</blockquote>
            {persona.scenario.success_criteria.length > 0 && (
              <ul className="criteria">{persona.scenario.success_criteria.map((c) => <li key={c}>{c}</li>)}</ul>
            )}
          </section>
        </div>

        {result?.feedback && (
          <section className="sheet-feedback">
            <h4>What they said about the model</h4>
            <div className="feedback">
              <RatingsRadar ratings={result.feedback.ratings} priorities={persona.priorities} size={160} />
              <div>
                {result.feedback.quote && <blockquote>“{result.feedback.quote}”</blockquote>}
                <p>{result.feedback.summary}</p>
                <div className="hl">
                  {result.feedback.highlights.map((h, i) => <span key={`h${i}`} className="pill pill-ok">＋ {h}</span>)}
                  {result.feedback.complaints.map((c, i) => <span key={`c${i}`} className="pill pill-err">− {c}</span>)}
                </div>
              </div>
            </div>
          </section>
        )}

        {onToggle && (
          <div className="form-actions">
            <button className={selected ? 'close-button' : 'run-button small'} onClick={onToggle}>
              {selected ? 'Exclude from this run' : 'Include in this run'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
