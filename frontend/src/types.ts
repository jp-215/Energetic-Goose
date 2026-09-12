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

// ---- Coding Hub --------------------------------------------------------------

export type HubRole = 'planner' | 'engineer' | 'integrator'

export interface TaskSpec {
  id: string
  title: string
  description: string
  deliverables: string[]
}

export interface AgentSpec {
  id: string
  name: string
  role: string
  specialty: string
  tasks: TaskSpec[]
  parent_id: string | null
  depth: number
  summoned_reason: string | null
}

export interface TeamPlan {
  analysis: string
  team_size: number
  rationale: string
  agents: AgentSpec[]
  integration_notes: string
  fallback: boolean
}

export interface CallTrace {
  role: string
  model: string
  system_prompt: string
  user_prompt: string
  raw_output: string
  latency_ms: number
  retries_used: number
  status: 'ok' | 'error'
  error: string | null
  prompt_tokens: number | null
  completion_tokens: number | null
  finish_reason: string | null
}

export interface WorkspaceFile {
  path: string
  content: string
  author: string
}

export interface HelpRequest {
  role: string
  task: string
  reason: string
}

export interface AgentResult {
  agent_id: string
  status: 'ok' | 'error'
  summary: string
  notes: string
  files: WorkspaceFile[]
  help_request: HelpRequest | null
  helper_id: string | null
  call: CallTrace
}

export interface IntegrationResult {
  status: 'ok' | 'error'
  summary: string
  run_instructions: string
  files: WorkspaceFile[]
  call: CallTrace
}

export interface HubResponse {
  run_id: string
  title: string
  status: string
  plan: TeamPlan | null
  agents: AgentResult[]
  integration: IntegrationResult | null
  workspace: WorkspaceFile[]
  trace: Record<string, unknown>[]
  total_latency_ms: number
  total_calls: number
  total_retries: number
  error: string | null
}

export type HubPhase = 'idle' | 'planning' | 'building' | 'integrating' | 'closed' | 'error'

export type HubEvent =
  | {
      event: 'run_accepted'
      run_id: string
      title: string
      models: Record<HubRole, string>
      limits: Record<string, number>
      max_agents: number
    }
  | { event: 'planner_started'; model: string; max_agents: number }
  | { event: 'plan_ready'; plan: TeamPlan; call: CallTrace }
  | { event: 'team_assembled'; agent_ids: string[]; team_size: number }
  | { event: 'agent_started'; agent: AgentSpec; model: string }
  | { event: 'agent_summoned'; agent: AgentSpec; parent_id: string; request: HelpRequest }
  | { event: 'summon_denied'; agent_id: string; reason: string; request: HelpRequest }
  | { event: 'agent_result'; agent_id: string; result: AgentResult }
  | {
      event: 'file_conflict'
      path: string
      previous_author: string
      new_author: string
      resolution: string
    }
  | { event: 'file_rejected'; agent_id: string; path: string; reason: string }
  | { event: 'output_truncated'; agent_id: string; max_tokens: number }
  | { event: 'integration_started'; model: string; file_count: number }
  | { event: 'integration_result'; result: IntegrationResult }
  | { event: 'run_closed'; response: HubResponse }
  | { event: 'error'; detail: string }

/** A hub event as recorded by the UI: sequence number + server timestamp. */
export type TraceEntry = HubEvent & { seq: number; at_ms: number }
