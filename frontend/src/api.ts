import type { CourtEvent, PlatformInfo } from './types'

export interface ModelsInfo {
  platform: PlatformInfo
  models: string[]
}

export async function fetchModels(): Promise<ModelsInfo> {
  const res = await fetch('/api/models')
  if (!res.ok) throw new Error(`/api/models: ${res.status} ${await res.text()}`)
  return res.json()
}

export interface CasePayload {
  title: string
  context: string
  query: string
  model_overrides?: Record<string, string>
}

/** Event-driven court run: POSTs the case and dispatches each NDJSON event
 * from the stream the moment it arrives. */
export async function streamCase(
  payload: CasePayload,
  onEvent: (event: CourtEvent) => void,
): Promise<void> {
  const res = await fetch('/api/court/run/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok || !res.body) {
    let detail = await res.text()
    try {
      detail = JSON.parse(detail).detail ?? detail
    } catch {
      /* keep raw text */
    }
    throw new Error(`Court stream failed (${res.status}): ${detail}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let newline
    while ((newline = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, newline).trim()
      buffer = buffer.slice(newline + 1)
      if (line) onEvent(JSON.parse(line) as CourtEvent)
    }
  }
  const tail = buffer.trim()
  if (tail) onEvent(JSON.parse(tail) as CourtEvent)
}
