const LABELS: Record<string, string> = {
  idle: 'idle',
  waiting: 'waiting',
  deliberating: 'deliberating',
  done: 'done',
  error: 'error',
}

export default function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge badge-${status}`}>{LABELS[status] ?? status}</span>
}
