export default function VerdictChip({ verdict, large }: { verdict: string; large?: boolean }) {
  const key = verdict.toLowerCase()
  return (
    <span className={`verdict-chip verdict-${key} ${large ? 'verdict-large' : ''}`}>{verdict}</span>
  )
}
