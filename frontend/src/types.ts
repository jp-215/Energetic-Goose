export type Role = 'simple' | 'complex' | 'judge'

export interface RoleResult {
  role: Role
  model: string
  answer: string
  verdict: string
  confidence: number | null
  rationale: string
  latency_ms: number
  retries_used: number
  status: 'ok' | 'error'
  error: string | null
}

export interface CaseResponse {
  case_id: string
  title: string
  final_verdict: string
  judge_rationale: string
  roles: Record<Role, RoleResult>
  total_latency_ms: number
  total_retries: number
  status: string
  error: string | null
}

export interface PlatformInfo {
  id: string
  label: string
}

export type NodeStatus = 'idle' | 'waiting' | 'deliberating' | 'done' | 'error'

export type CourtPhase = 'idle' | 'counsels' | 'judge' | 'closed' | 'error'

export type CourtEvent =
  | { event: 'case_accepted'; case_id: string; title: string }
  | { event: 'role_result'; role: Role; result: RoleResult }
  | { event: 'judge_started' }
  | { event: 'case_closed'; response: CaseResponse }
  | { event: 'error'; detail: string }
