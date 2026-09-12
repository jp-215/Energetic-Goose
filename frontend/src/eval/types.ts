// Types mirroring services/court-orchestrator/app/models/evaluation.py + persona.py

export interface CatalogEntry {
  id: string
  vendor: string
  region: string
}

export interface BenchmarkInfo {
  name: string
  display_name: string
  source: string
  task_type: 'multiple_choice' | 'numeric'
  description: string
  item_count: number
  bundled_sample: boolean
}

export interface GraphStatus {
  backend: 'neo4j' | 'memory' | 'unavailable'
  connected: boolean
  uri?: string
  nodes?: number
  relationships?: number
  labels?: Record<string, number>
  error?: string
}

export interface EvalMeta {
  catalog: CatalogEntry[]
  platform_models: string[]
  benchmarks: BenchmarkInfo[]
  weights: { benchmark: number; agents: number }
  defaults: {
    items_per_benchmark: number
    max_items_per_benchmark: number
    agent_turns: number
    max_agent_turns: number
  }
  simulator_model: string
  mock_mode: boolean
  graph: GraphStatus
}

export interface Scenario {
  title: string
  goal: string
  opening_message: string
  success_criteria: string[]
}

export interface Persona {
  id: string
  name: string
  avatar: string
  tagline: string
  age?: number | null
  occupation: string
  language: string
  background: string
  personality_traits: string[]
  communication_style: string
  expertise_level: 'novice' | 'intermediate' | 'expert'
  patience: number
  strictness: number
  priorities: Record<string, number>
  scenario: Scenario
  builtin: boolean
}

export interface Turn {
  id: string
  index: number
  role: 'user' | 'assistant'
  content: string
  latency_ms: number
  error?: string | null
}

export interface Feedback {
  ratings: Record<string, number>
  would_use_again: boolean
  summary: string
  highlights: string[]
  complaints: string[]
  quote: string
  raw?: string
}

export interface AgentResult {
  agent_id: string
  agent_name: string
  avatar: string
  scenario_title: string
  priorities: Record<string, number>
  turns: Turn[]
  feedback: Feedback | null
  score: number
  status: 'ok' | 'partial' | 'error'
  error?: string | null
}

export interface BenchmarkItemResult {
  id: string
  question: string
  choices?: string[] | null
  response: string
  expected: string
  predicted: string | null
  correct: boolean
  latency_ms: number
  error?: string | null
}

export interface BenchmarkResult {
  name: string
  display_name: string
  source: string
  task_type: string
  total: number
  correct: number
  score: number
  errors: number
  avg_latency_ms: number
  items: BenchmarkItemResult[]
}

export type SessionStatus = 'running' | 'done' | 'error'
export type SessionStage = 'queued' | 'benchmarks' | 'agents' | 'scoring' | 'done' | 'error'

export interface Session {
  id: string
  label: string
  model: string
  vendor: string
  region: string
  simulator_model: string
  created_at: string
  finished_at: string | null
  status: SessionStatus
  stage: SessionStage
  weights: { benchmark: number; agents: number }
  config: {
    items_per_benchmark: number
    agent_turns: number
    seed: number
    agent_ids: string[]
    benchmarks: string[]
    mock_mode: boolean
  }
  benchmark_score: number | null
  agent_score: number | null
  final_score: number | null
  benchmarks: BenchmarkResult[]
  agents: AgentResult[]
  error: string | null
}

export interface SessionSummary {
  id: string
  label: string
  model: string
  vendor: string
  region: string
  created_at: string
  finished_at: string | null
  status: SessionStatus
  stage: SessionStage
  benchmark_score: number | null
  agent_score: number | null
  final_score: number | null
  agent_count: number
  benchmark_count: number
}

export interface RankingEntry {
  rank: number
  model: string
  vendor: string
  region: string
  sessions: number
  best_final: number
  latest_final: number
  avg_final: number
  avg_benchmark: number
  avg_agents: number
  best_session_id: string
  latest_session_id: string
  last_evaluated: string
}

export interface GraphNode {
  id: string
  label: string
  properties: Record<string, unknown>
}

export interface GraphRelationship {
  id: string
  type: string
  from: string
  to: string
  properties: Record<string, unknown>
}

export interface GraphResponse {
  backend: string
  session_id: string
  cypher: string
  nodes: GraphNode[]
  relationships: GraphRelationship[]
}

export interface EvaluationPayload {
  models: string[]
  agent_ids?: string[]
  benchmarks?: string[]
  items_per_benchmark?: number
  agent_turns?: number
  benchmark_weight?: number
  simulator_model?: string
  seed?: number
  label?: string
}

export type EvalEvent =
  | { event: 'session_created'; session: SessionSummary }
  | { event: 'stage'; session_id: string; stage: SessionStage; benchmarks?: string[]; agents?: string[] }
  | {
      event: 'benchmark_item'
      session_id: string
      benchmark: string
      done: number
      total: number
      correct: boolean
      item_id: string
    }
  | { event: 'benchmark_result'; session_id: string; result: Omit<BenchmarkResult, 'items'> }
  | { event: 'agent_turn'; session_id: string; agent_id: string; agent_name: string; turn: Turn }
  | {
      event: 'agent_feedback'
      session_id: string
      agent_id: string
      agent_name: string
      score: number
      status: AgentResult['status']
      feedback: Feedback | null
    }
  | { event: 'session_done'; session: Session }
  | { event: 'all_done'; models: string[] }
  | { event: 'error'; detail: string }

export const DIMENSIONS = ['helpfulness', 'accuracy', 'clarity', 'tone', 'trust'] as const

export const REGION_FLAG: Record<string, string> = {
  CN: '🇨🇳',
  US: '🇺🇸',
  EU: '🇪🇺',
  IL: '🇮🇱',
  '?': '🌐',
}
