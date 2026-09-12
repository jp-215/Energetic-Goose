import type { Persona } from '../types'
import { scoreColor } from './ScoreTile'

/** Round emoji avatar with the name underneath. Click → details; optional
 * selection ring and score badge. */
export default function PersonaAvatar({
  persona,
  selected,
  score,
  status,
  size = 64,
  onClick,
  onToggle,
}: {
  persona: Pick<Persona, 'id' | 'name' | 'avatar' | 'tagline'>
  selected?: boolean
  score?: number | null
  status?: string
  size?: number
  onClick?: () => void
  onToggle?: () => void
}) {
  const short = persona.name.replace(/\s*\(.*\)$/, '')
  return (
    <div className={`avatar-card ${selected ? 'is-selected' : ''} ${selected === false ? 'is-off' : ''} status-${status ?? ''}`} title={persona.tagline}>
      <button className="avatar-circle" style={{ width: size, height: size, fontSize: size * 0.5 }} onClick={onClick} aria-label={`About ${persona.name}`}>
        {persona.avatar}
        {score != null && <span className="avatar-score" style={{ background: scoreColor(score) }}>{Math.round(score)}</span>}
        {status === 'talking' && <span className="avatar-pulse" />}
      </button>
      <div className="avatar-name">{short}</div>
      {onToggle && (
        <label className="avatar-toggle" onClick={(e) => e.stopPropagation()}>
          <input type="checkbox" checked={!!selected} onChange={onToggle} /> <span>{selected ? 'in run' : 'excluded'}</span>
        </label>
      )}
    </div>
  )
}
