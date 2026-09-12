import { create } from 'zustand'
import { fetchModels, streamCase } from './api'
import type {
  CaseResponse,
  CourtPhase,
  NodeStatus,
  PlatformInfo,
  Role,
  RoleResult,
} from './types'

const IDLE_STATUS: Record<Role, NodeStatus> = { simple: 'idle', complex: 'idle', judge: 'idle' }

interface CourtState {
  title: string
  context: string
  query: string

  // Models are event-driven, never a page-load precondition.
  models: string[]
  platform: PlatformInfo | null
  modelsLoading: boolean
  overrides: Partial<Record<Role, string>>

  phase: CourtPhase
  roleStatus: Record<Role, NodeStatus>
  roleResults: Partial<Record<Role, RoleResult>>
  result: CaseResponse | null
  error: string | null

  setField: (field: 'title' | 'context' | 'query', value: string) => void
  setOverride: (role: Role, model: string) => void
  ensureModels: () => Promise<void>
  startCase: () => Promise<void>
  closeCase: () => void
}

export const useCourtStore = create<CourtState>((set, get) => ({
  title: 'Orchard Lane Fence Dispute',
  context:
    'The plaintiff hired the defendant to build a cedar fence for $4,200, half paid up front. ' +
    'The contract specified completion within 30 days. The defendant finished on day 52, citing ' +
    'two weeks of heavy rain documented by local weather records. The plaintiff refuses to pay ' +
    'the remaining balance and claims $600 in damages for a relocated garden party.',
  query:
    'Is the defendant entitled to the remaining balance, and does the plaintiff have a valid damages claim?',

  models: [],
  platform: null,
  modelsLoading: false,
  overrides: {},

  phase: 'idle',
  roleStatus: { ...IDLE_STATUS },
  roleResults: {},
  result: null,
  error: null,

  setField: (field, value) => set({ [field]: value }),

  setOverride: (role, model) =>
    set((state) => {
      const overrides = { ...state.overrides }
      if (model) overrides[role] = model
      else delete overrides[role]
      return { overrides }
    }),

  ensureModels: async () => {
    const { models, modelsLoading } = get()
    if (models.length > 0 || modelsLoading) return
    set({ modelsLoading: true })
    try {
      const info = await fetchModels()
      set({ models: info.models, platform: info.platform, modelsLoading: false })
    } catch (err) {
      set({ modelsLoading: false, error: err instanceof Error ? err.message : String(err) })
    }
  },

  startCase: async () => {
    const { title, context, query, overrides, phase } = get()
    if (phase === 'counsels' || phase === 'judge' || !title.trim()) return
    set({
      phase: 'counsels',
      result: null,
      error: null,
      roleResults: {},
      roleStatus: { simple: 'deliberating', complex: 'deliberating', judge: 'waiting' },
    })
    const hasOverrides = Object.keys(overrides).length > 0
    try {
      await streamCase(
        {
          title,
          context,
          query,
          ...(hasOverrides ? { model_overrides: overrides as Record<string, string> } : {}),
        },
        (event) => {
          if (event.event === 'role_result') {
            set((state) => ({
              roleResults: { ...state.roleResults, [event.role]: event.result },
              roleStatus: {
                ...state.roleStatus,
                [event.role]: event.result.status === 'ok' ? 'done' : 'error',
              },
            }))
          } else if (event.event === 'judge_started') {
            set((state) => ({
              phase: 'judge',
              roleStatus: { ...state.roleStatus, judge: 'deliberating' },
            }))
          } else if (event.event === 'case_closed') {
            set({
              phase: event.response.status === 'ok' ? 'closed' : 'error',
              result: event.response,
              error: event.response.error,
            })
          } else if (event.event === 'error') {
            set({ phase: 'error', error: event.detail })
          }
        },
      )
    } catch (err) {
      set({ phase: 'error', error: err instanceof Error ? err.message : String(err) })
    }
  },

  closeCase: () =>
    set({
      phase: 'idle',
      roleStatus: { ...IDLE_STATUS },
      roleResults: {},
      result: null,
      error: null,
    }),
}))
