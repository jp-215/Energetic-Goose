import type { Turn } from '../types'

export default function Transcript({ turns, agentName, avatar, model }: { turns: Turn[]; agentName: string; avatar: string; model: string }) {
  if (turns.length === 0) return <div className="muted">No turns yet.</div>
  return (
    <div className="transcript">
      {turns.map((t) => (
        <div key={t.id} className={`bubble bubble-${t.role} ${t.error ? 'bubble-error' : ''}`}>
          <div className="bubble-meta">
            <span>{t.role === 'user' ? `${avatar} ${agentName}` : `🤖 ${model}`}</span>
            <span className="muted">#{t.index}{t.latency_ms ? ` · ${t.latency_ms} ms` : ''}</span>
          </div>
          <div className="bubble-body">{t.content}</div>
        </div>
      ))}
    </div>
  )
}
