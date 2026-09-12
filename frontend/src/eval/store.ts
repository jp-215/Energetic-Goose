import { create } from 'zustand'
import { fetchEvalMeta, fetchPersonas, streamEvaluation, streamRerun } from './api'
import type {
  EvalEvent,
  EvalMeta,
  EvaluationPayload,
  Feedback,
  Persona,
  Session,
  SessionStage,
  Turn,
} from './types'

export interface AgentProgress {
  id: string
  name: string
  avatar: string
  turns: Turn[]
  feedback: Feedback | null
  score: number | null
  status: 'waiting' | 'talking' | 'ok' | 'partial' | 'error'
}

export interface BenchmarkProgress {
  name: string
  done: number
  total: number
  correct: number
  score: number | null
}

export interface RunProgress {
  sessionId: string
  model: string
  stage: SessionStage | 'queued'
  benchmarks: Record<string, BenchmarkProgress>
  agents: Record<string, AgentProgress>
  session: Session | null
}

interface EvalState {
  meta: EvalMeta | null
  personas: Persona[]
  loading: boolean
  loadError: string | null

  // form
  selectedModels: string[]
  agentIds: string[]
  benchmarkNames: string[]
  itemsPerBenchmark: number
  agentTurns: number
  benchmarkWeight: number
  label: string

  // run
  running: boolean
  runs: RunProgress[]
  log: string[]
  runError: string | null

  load: (force?: boolean) => Promise<void>
  setPersonas: (personas: Persona[]) => void
  addModel: (model: string) => void
  removeModel: (model: string) => void
  toggleAgent: (id: string) => void
  toggleBenchmark: (name: string) => void
  setNumber: (field: 'itemsPerBenchmark' | 'agentTurns' | 'benchmarkWeight', v: number) => void
  setLabel: (label: string) => void
  startRun: () => Promise<void>
  rerun: (sessionId: string) => Promise<void>
  clearRuns: () => void
}

function emptyAgent(p: Persona): AgentProgress {
  return { id: p.id, name: p.name, avatar: p.avatar, turns: [], feedback: null, score: null, status: 'waiting' }
}

export const useEvalStore = create<EvalState>((set, get) => ({
  meta: null,
  personas: [],
  loading: false,
  loadError: null,

  selectedModels: [],
  agentIds: [],
  benchmarkNames: [],
  itemsPerBenchmark: 8,
  agentTurns: 3,
  benchmarkWeight: 0.5,
  label: '',

  running: false,
  runs: [],
  log: [],
  runError: null,

  load: async (force = false) => {
    if (get().loading || (get().meta && !force)) return
    set({ loading: true, loadError: null })
    try {
      const [meta, personas] = await Promise.all([fetchEvalMeta(), fetchPersonas()])
      set((s) => ({
        meta,
        personas: personas.personas,
        loading: false,
        agentIds: s.agentIds.length ? s.agentIds : personas.personas.map((p) => p.id),
        benchmarkNames: s.benchmarkNames.length ? s.benchmarkNames : meta.benchmarks.map((b) => b.name),
        itemsPerBenchmark: s.meta ? s.itemsPerBenchmark : meta.defaults.items_per_benchmark,
        agentTurns: s.meta ? s.agentTurns : meta.defaults.agent_turns,
        benchmarkWeight: s.meta ? s.benchmarkWeight : meta.weights.benchmark,
      }))
    } catch (err) {
      set({ loading: false, loadError: err instanceof Error ? err.message : String(err) })
    }
  },

  setPersonas: (personas) =>
    set((s) => ({
      personas,
      agentIds: s.agentIds.filter((id) => personas.some((p) => p.id === id)),
    })),

  addModel: (model) => {
    const m = model.trim()
    if (!m) return
    set((s) => (s.selectedModels.includes(m) ? {} : { selectedModels: [...s.selectedModels, m] }))
  },
  removeModel: (model) => set((s) => ({ selectedModels: s.selectedModels.filter((m) => m !== model) })),
  toggleAgent: (id) =>
    set((s) => ({
      agentIds: s.agentIds.includes(id) ? s.agentIds.filter((a) => a !== id) : [...s.agentIds, id],
    })),
  toggleBenchmark: (name) =>
    set((s) => ({
      benchmarkNames: s.benchmarkNames.includes(name)
        ? s.benchmarkNames.filter((b) => b !== name)
        : [...s.benchmarkNames, name],
    })),
  setNumber: (field, v) => set({ [field]: v }),
  setLabel: (label) => set({ label }),

  startRun: async () => {
    const s = get()
    if (s.running || s.selectedModels.length === 0) return
    const payload: EvaluationPayload = {
      models: s.selectedModels,
      agent_ids: s.agentIds,
      benchmarks: s.benchmarkNames,
      items_per_benchmark: s.itemsPerBenchmark,
      agent_turns: s.agentTurns,
      benchmark_weight: s.benchmarkWeight,
      label: s.label || undefined,
    }
    set({ running: true, runs: [], log: [], runError: null })
    try {
      await streamEvaluation(payload, (event) => applyEvent(event, set, get))
    } catch (err) {
      set({ runError: err instanceof Error ? err.message : String(err) })
    } finally {
      set({ running: false })
    }
  },

  rerun: async (sessionId) => {
    if (get().running) return
    set({ running: true, runs: [], log: [`rerunning session ${sessionId}`], runError: null })
    try {
      await streamRerun(sessionId, (event) => applyEvent(event, set, get))
    } catch (err) {
      set({ runError: err instanceof Error ? err.message : String(err) })
    } finally {
      set({ running: false })
    }
  },

  clearRuns: () => set({ runs: [], log: [], runError: null }),
}))

type Set = (fn: (s: EvalState) => Partial<EvalState>) => void
type Get = () => EvalState

function applyEvent(event: EvalEvent, set: Set, get: Get) {
  const logLine = (line: string) => set((s) => ({ log: [...s.log.slice(-199), line] }))
  const patchRun = (sessionId: string, fn: (r: RunProgress) => RunProgress) =>
    set((s) => ({ runs: s.runs.map((r) => (r.sessionId === sessionId ? fn(r) : r)) }))

  switch (event.event) {
    case 'session_created': {
      const personas = get().personas
      const agentIds = get().agentIds.length ? get().agentIds : personas.map((p) => p.id)
      const agents: Record<string, AgentProgress> = {}
      for (const id of agentIds) {
        const p = personas.find((x) => x.id === id)
        if (p) agents[id] = emptyAgent(p)
      }
      set((s) => ({
        runs: [
          ...s.runs,
          { sessionId: event.session.id, model: event.session.model, stage: 'queued', benchmarks: {}, agents, session: null },
        ],
      }))
      logLine(`session ${event.session.id} created for ${event.session.model}`)
      break
    }
    case 'stage':
      patchRun(event.session_id, (r) => {
        const benchmarks = { ...r.benchmarks }
        for (const name of event.benchmarks ?? []) {
          benchmarks[name] = benchmarks[name] ?? { name, done: 0, total: 0, correct: 0, score: null }
        }
        return { ...r, stage: event.stage, benchmarks }
      })
      logLine(`[${event.session_id}] stage → ${event.stage}`)
      break
    case 'benchmark_item':
      patchRun(event.session_id, (r) => {
        const prev = r.benchmarks[event.benchmark] ?? { name: event.benchmark, done: 0, total: 0, correct: 0, score: null }
        return {
          ...r,
          benchmarks: {
            ...r.benchmarks,
            [event.benchmark]: { ...prev, done: event.done, total: event.total, correct: prev.correct + (event.correct ? 1 : 0) },
          },
        }
      })
      break
    case 'benchmark_result':
      patchRun(event.session_id, (r) => ({
        ...r,
        benchmarks: {
          ...r.benchmarks,
          [event.result.name]: {
            name: event.result.name,
            done: event.result.total,
            total: event.result.total,
            correct: event.result.correct,
            score: event.result.score,
          },
        },
      }))
      logLine(`[${event.session_id}] ${event.result.display_name}: ${event.result.score}% (${event.result.correct}/${event.result.total})`)
      break
    case 'agent_turn':
      patchRun(event.session_id, (r) => {
        const prev = r.agents[event.agent_id] ?? {
          id: event.agent_id, name: event.agent_name, avatar: '🙂', turns: [], feedback: null, score: null, status: 'talking' as const,
        }
        return { ...r, agents: { ...r.agents, [event.agent_id]: { ...prev, status: 'talking', turns: [...prev.turns, event.turn] } } }
      })
      break
    case 'agent_feedback':
      patchRun(event.session_id, (r) => {
        const prev = r.agents[event.agent_id]
        if (!prev) return r
        return { ...r, agents: { ...r.agents, [event.agent_id]: { ...prev, status: event.status, score: event.score, feedback: event.feedback } } }
      })
      logLine(`[${event.session_id}] ${event.agent_name} scored the model ${event.score}/100`)
      break
    case 'session_done':
      patchRun(event.session.id, (r) => ({ ...r, stage: event.session.stage, session: event.session }))
      logLine(`[${event.session.id}] ${event.session.model} final ${event.session.final_score ?? '—'} (benchmarks ${event.session.benchmark_score}, agents ${event.session.agent_score})`)
      break
    case 'all_done':
      logLine(`all done: ${event.models.join(', ')}`)
      break
    case 'error':
      set(() => ({ runError: event.detail }))
      logLine(`error: ${event.detail}`)
      break
  }
}
