import type { CourtEvent, HubEvent, HubRole, PlatformInfo, WorkspaceFile } from './types'

export interface ModelsInfo {
  platform: PlatformInfo
  models: string[]
}

export async function fetchModels(): Promise<ModelsInfo> {
  const res = await fetch('/api/models')
  if (!res.ok) throw new Error(`/api/models: ${res.status} ${await res.text()}`)
  return res.json()
}

async function failureMessage(label: string, res: Response): Promise<string> {
  let detail = await res.text()
  try {
    detail = JSON.parse(detail).detail ?? detail
  } catch {
    /* keep raw text */
  }
  return `${label} (${res.status}): ${detail}`
}

async function postJson<T>(url: string, payload: unknown, label: string): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await failureMessage(label, res))
  return res.json()
}

/** POSTs a payload and dispatches each NDJSON line from the response stream
 * the moment it arrives. Shared by the court and The Firm. */
async function streamNdjson<E>(
  url: string,
  payload: unknown,
  label: string,
  onEvent: (event: E) => void,
): Promise<void> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok || !res.body) throw new Error(await failureMessage(label, res))

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
      if (line) onEvent(JSON.parse(line) as E)
    }
  }
  const tail = buffer.trim()
  if (tail) onEvent(JSON.parse(tail) as E)
}

// ---- Court ---------------------------------------------------------------------

export interface CasePayload {
  title: string
  context: string
  query: string
  model_overrides?: Record<string, string>
}

export function streamCase(payload: CasePayload, onEvent: (event: CourtEvent) => void) {
  return streamNdjson<CourtEvent>('/api/court/run/stream', payload, 'Court stream failed', onEvent)
}

// ---- The Firm ------------------------------------------------------------------

export interface HubPayload {
  title: string
  context: string
  goal: string
  max_agents?: number
  model_overrides?: Partial<Record<HubRole, string>>
}

export function streamHub(payload: HubPayload, onEvent: (event: HubEvent) => void) {
  return streamNdjson<HubEvent>('/api/hub/run/stream', payload, 'Hub stream failed', onEvent)
}

export interface HubRolesInfo {
  hub_models: Record<HubRole, string>
  hub_instructions: Record<HubRole, string>
  limits: Record<string, number>
}

export async function fetchHubRoles(): Promise<HubRolesInfo> {
  const res = await fetch('/api/hub/roles')
  if (!res.ok) throw new Error(await failureMessage('/api/hub/roles', res))
  return res.json()
}

export interface ExportResult {
  run_id: string
  path: string
  file_count: number
}

export function exportWorkspace(
  run_id: string,
  files: WorkspaceFile[],
  manifest: Record<string, unknown>,
): Promise<ExportResult> {
  return postJson('/api/hub/export', { run_id, files, manifest }, 'Export failed')
}

export interface PublishResult {
  run_id: string
  repo_url: string
  path: string
}

export function publishWorkspace(
  run_id: string,
  repo_name: string,
  isPrivate: boolean,
  description: string,
): Promise<PublishResult> {
  return postJson(
    '/api/hub/publish',
    { run_id, repo_name, private: isPrivate, description },
    'Publish failed',
  )
}
