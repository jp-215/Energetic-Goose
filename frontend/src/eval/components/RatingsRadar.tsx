import { DIMENSIONS } from '../types'

/** Pentagon radar of the five feedback dimensions (1-10), with optional
 * priority weights drawn as a faint second polygon. */
export default function RatingsRadar({
  ratings,
  priorities,
  size = 160,
}: {
  ratings: Record<string, number>
  priorities?: Record<string, number>
  size?: number
}) {
  const cx = size / 2
  const cy = size / 2
  const R = size / 2 - 22
  const n = DIMENSIONS.length
  const angle = (i: number) => -Math.PI / 2 + (2 * Math.PI * i) / n
  const point = (i: number, v: number) => [cx + R * v * Math.cos(angle(i)), cy + R * v * Math.sin(angle(i))]
  const poly = (vals: number[]) => vals.map((v, i) => point(i, v).join(',')).join(' ')

  const ratingVals = DIMENSIONS.map((d) => (ratings[d] ?? 0) / 10)
  const maxPriority = priorities ? Math.max(...DIMENSIONS.map((d) => priorities[d] ?? 0), 0.0001) : 1
  const priorityVals = priorities ? DIMENSIONS.map((d) => (priorities[d] ?? 0) / maxPriority) : null

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="radar">
      {[0.25, 0.5, 0.75, 1].map((ring) => (
        <polygon key={ring} points={poly(DIMENSIONS.map(() => ring))} fill="none" stroke="var(--border)" strokeWidth={1} />
      ))}
      {DIMENSIONS.map((_, i) => {
        const [x, y] = point(i, 1)
        return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="var(--border)" strokeWidth={1} />
      })}
      {priorityVals && (
        <polygon points={poly(priorityVals)} fill="rgba(122,162,247,0.12)" stroke="var(--accent-2)" strokeDasharray="3 3" strokeWidth={1} />
      )}
      <polygon points={poly(ratingVals)} fill="rgba(212,162,76,0.25)" stroke="var(--accent)" strokeWidth={2} />
      {DIMENSIONS.map((d, i) => {
        const [x, y] = point(i, 1.22)
        return (
          <text key={d} x={x} y={y} textAnchor="middle" dominantBaseline="central" className="radar-label">
            {d} {ratings[d] ?? '–'}
          </text>
        )
      })}
    </svg>
  )
}
