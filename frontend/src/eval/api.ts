import type {
  EvalEvent,
  EvalMeta,
  EvaluationPayload,
  GraphResponse,
  Persona,
  RankingEntry,
  Session,
  SessionSummary,
} from './types'

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = await res.text()
    try {
      detail = JSON.parse(detail).detail ?? detail
    } catch {
      /* keep raw */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.json()
}

const JSON_HEADERS = { 'Content-Type': 'application/json' }

export const fetchEvalMeta = () => fetch('/api/eval/meta').then((r) => json<EvalMeta>(r))

export const fetchPersonas = () =>
  fetch('/api/eval/personas').then((r) => json<{ personas: Persona[]; dimensions: string[] }>(r))

export const importPersonas = (personas: unknown) =>
  fetch('/api/eval/personas/import', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(personas),
  }).then((r) => json<{ imported: string[]; personas: Persona[] }>(r))

export const updatePersona = (id: string, persona: Persona) =>
  fetch(`/api/eval/personas/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: JSON_HEADERS,
    body: JSON.stringify(persona),
  }).then((r) => json<Persona>(r))

export const deletePersona = (id: string) =>
  fetch(`/api/eval/personas/${encodeURIComponent(id)}`, { method: 'DELETE' }).then((r) =>
    json<{ deleted: string }>(r),
  )

export const resetPersonas = () =>
  fetch('/api/eval/personas/reset', { method: 'POST' }).then((r) =>
    json<{ personas: Persona[] }>(r),
  )

export const fetchSessions = () =>
  fetch('/api/eval/sessions').then((r) => json<{ sessions: SessionSummary[] }>(r))

export const fetchSession = (id: string) =>
  fetch(`/api/eval/sessions/${encodeURIComponent(id)}`).then((r) => json<Session>(r))

export const deleteSession = (id: string) =>
  fetch(`/api/eval/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }).then((r) =>
    json<{ deleted: string }>(r),
  )

export const fetchSessionGraph = (id: string) =>
  fetch(`/api/eval/sessions/${encodeURIComponent(id)}/graph`).then((r) => json<GraphResponse>(r))

export const fetchRankings = () =>
  fetch('/api/eval/rankings').then((r) =>
    json<{ rankings: RankingEntry[]; weights: { benchmark: number; agents: number } }>(r),
  )

export const runCypher = (query: string) =>
  fetch('/api/eval/graph/cypher', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ query }),
  }).then((r) => json<{ columns: string[]; rows: unknown[][] }>(r))

/** POST and dispatch each NDJSON line as it arrives. */
async function streamNdjson(url: string, body: unknown, onEvent: (e: EvalEvent) => void) {
  const res = await fetch(url, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok || !res.body) {
    let detail = await res.text()
    try {
      detail = JSON.parse(detail).detail ?? detail
    } catch {
      /* keep raw */
    }
    throw new Error(`Evaluation stream failed (${res.status}): ${JSON.stringify(detail)}`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let nl
    while ((nl = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, nl).trim()
      buffer = buffer.slice(nl + 1)
      if (line) onEvent(JSON.parse(line) as EvalEvent)
    }
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer) as EvalEvent)
}

export const streamEvaluation = (payload: EvaluationPayload, onEvent: (e: EvalEvent) => void) =>
  streamNdjson('/api/eval/run/stream', payload, onEvent)

export const streamRerun = (sessionId: string, onEvent: (e: EvalEvent) => void) =>
  streamNdjson(`/api/eval/sessions/${encodeURIComponent(sessionId)}/rerun/stream`, undefined, onEvent)
