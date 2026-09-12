export function scoreColor(score: number | null | undefined): string {
  if (score == null) return 'var(--muted)'
  if (score >= 80) return 'var(--ok)'
  if (score >= 60) return 'var(--accent)'
  if (score >= 40) return 'var(--run)'
  return 'var(--err)'
}

export function fmt(score: number | null | undefined, digits = 1): string {
  return score == null ? '—' : score.toFixed(digits)
}

/** Big score with a ring. */
export function ScoreRing({ score, label, size = 120, sub }: { score: number | null; label: string; size?: number; sub?: string }) {
  const r = (size - 12) / 2
  const c = 2 * Math.PI * r
  const pct = Math.max(0, Math.min(100, score ?? 0))
  return (
    <div className="score-ring" style={{ width: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size / 2} cy={size / 2} r={r} stroke="var(--border)" strokeWidth={8} fill="none" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={scoreColor(score)}
          strokeWidth={8}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={`${(pct / 100) * c} ${c}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" className="score-ring-value">
          {fmt(score)}
        </text>
      </svg>
      <div className="score-ring-label">{label}</div>
      {sub && <div className="score-ring-sub">{sub}</div>}
    </div>
  )
}

export function ScoreBar({ value, max = 100, color, height = 8 }: { value: number | null; max?: number; color?: string; height?: number }) {
  const pct = value == null ? 0 : Math.max(0, Math.min(100, (value / max) * 100))
  return (
    <div className="score-bar" style={{ height }}>
      <div className="score-bar-fill" style={{ width: `${pct}%`, background: color ?? scoreColor(value == null ? null : (value / max) * 100) }} />
    </div>
  )
}
