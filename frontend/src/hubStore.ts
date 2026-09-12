import { create } from 'zustand'
import { exportWorkspace, publishWorkspace, streamHub } from './api'
import type {
  AgentResult,
  AgentSpec,
  CallTrace,
  HubEvent,
  HubPhase,
  HubResponse,
  HubRole,
  IntegrationResult,
  NodeStatus,
  TeamPlan,
  TraceEntry,
  WorkspaceFile,
} from './types'

type AsyncStatus = 'idle' | 'working' | 'done' | 'error'

interface HubState {
  // Brief
  title: string
  context: string
  goal: string
  maxAgents: number
  overrides: Partial<Record<HubRole, string>>

  // Run
  phase: HubPhase
  runId: string | null
  plan: TeamPlan | null
  plannerStatus: NodeStatus
  plannerCall: CallTrace | null
  agents: Record<string, AgentSpec>
  agentOrder: string[]
  agentStatus: Record<string, NodeStatus>
  agentResults: Record<string, AgentResult>
  integratorStatus: NodeStatus
  integration: IntegrationResult | null
  workspace: Record<string, WorkspaceFile>
  trace: TraceEntry[]
  result: HubResponse | null
  error: string | null

  // Workspace panel
  selectedFile: string | null
  exportStatus: AsyncStatus
  exportPath: string | null
  exportError: string | null
  repoName: string
  repoPrivate: boolean
  publishStatus: AsyncStatus
  repoUrl: string | null
  publishError: string | null

  setField: (field: 'title' | 'context' | 'goal', value: string) => void
  setMaxAgents: (value: number) => void
  setOverride: (role: HubRole, model: string) => void
  startRun: () => Promise<void>
  resetRun: () => void
  selectFile: (path: string | null) => void
  setRepoName: (value: string) => void
  setRepoPrivate: (value: boolean) => void
  exportRun: () => Promise<void>
  publishRun: () => Promise<void>
}

const EMPTY_RUN = {
  phase: 'idle' as HubPhase,
  runId: null,
  plan: null,
  plannerStatus: 'idle' as NodeStatus,
  plannerCall: null,
  agents: {},
  agentOrder: [],
  agentStatus: {},
  agentResults: {},
  integratorStatus: 'idle' as NodeStatus,
  integration: null,
  workspace: {},
  trace: [],
  result: null,
  error: null,
  selectedFile: null,
  exportStatus: 'idle' as AsyncStatus,
  exportPath: null,
  exportError: null,
  publishStatus: 'idle' as AsyncStatus,
  repoUrl: null,
  publishError: null,
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60) || 'hub-project'
}

function mergeFiles(
  workspace: Record<string, WorkspaceFile>,
  files: WorkspaceFile[],
): Record<string, WorkspaceFile> {
  const next = { ...workspace }
  for (const file of files) next[file.path] = file
  return next
}

export const useHubStore = create<HubState>((set, get) => ({
  title: 'Task Tracker CLI',
  context:
    'A small command-line task tracker written in Python 3. Tasks live in a local JSON file. ' +
    'Users can add a task, list tasks, mark one done, and delete one. Keep it dependency-free.',
  goal:
    'Deliver a runnable project: the CLI module, a tiny test suite, and a README with setup ' +
    'and usage instructions.',
  maxAgents: 3,
  overrides: {},

  ...EMPTY_RUN,
  repoName: 'task-tracker-cli',
  repoPrivate: true,

  setField: (field, value) =>
    set((state) => ({
      [field]: value,
      ...(field === 'title' && state.runId === null ? { repoName: slugify(value) } : {}),
    })),

  setMaxAgents: (value) => set({ maxAgents: Math.min(5, Math.max(1, Math.round(value))) }),

  setOverride: (role, model) =>
    set((state) => {
      const overrides = { ...state.overrides }
      if (model) overrides[role] = model
      else delete overrides[role]
      return { overrides }
    }),

  startRun: async () => {
    const { title, context, goal, maxAgents, overrides, phase } = get()
    if (phase === 'planning' || phase === 'building' || phase === 'integrating') return
    if (!title.trim()) return
    set({ ...EMPTY_RUN, phase: 'planning', plannerStatus: 'deliberating' })

    let seq = 0
    const record = (event: HubEvent) => {
      const at_ms = (event as { at_ms?: number }).at_ms ?? 0
      const entry = { ...event, seq: seq++, at_ms } as TraceEntry
      set((state) => ({ trace: [...state.trace, entry] }))
    }

    const hasOverrides = Object.keys(overrides).length > 0
    try {
      await streamHub(
        {
          title,
          context,
          goal,
          max_agents: maxAgents,
          ...(hasOverrides ? { model_overrides: overrides } : {}),
        },
        (event) => {
          record(event)
          switch (event.event) {
            case 'run_accepted':
              set({ runId: event.run_id })
              break
            case 'plan_ready': {
              const agents: Record<string, AgentSpec> = {}
              const agentStatus: Record<string, NodeStatus> = {}
              for (const agent of event.plan.agents) {
                agents[agent.id] = agent
                agentStatus[agent.id] = 'waiting'
              }
              set({
                phase: 'building',
                plan: event.plan,
                plannerCall: event.call,
                plannerStatus: event.call.status === 'ok' && !event.plan.fallback ? 'done' : 'error',
                agents,
                agentOrder: event.plan.agents.map((a) => a.id),
                agentStatus,
                integratorStatus: 'waiting',
              })
              break
            }
            case 'agent_started':
              set((state) => ({
                agents: { ...state.agents, [event.agent.id]: event.agent },
                agentOrder: state.agentOrder.includes(event.agent.id)
                  ? state.agentOrder
                  : [...state.agentOrder, event.agent.id],
                agentStatus: { ...state.agentStatus, [event.agent.id]: 'deliberating' },
              }))
              break
            case 'agent_summoned':
              set((state) => ({
                agents: { ...state.agents, [event.agent.id]: event.agent },
                agentOrder: [...state.agentOrder, event.agent.id],
                agentStatus: { ...state.agentStatus, [event.agent.id]: 'waiting' },
              }))
              break
            case 'agent_result':
              set((state) => ({
                agentResults: { ...state.agentResults, [event.agent_id]: event.result },
                agentStatus: {
                  ...state.agentStatus,
                  [event.agent_id]: event.result.status === 'ok' ? 'done' : 'error',
                },
                workspace: mergeFiles(state.workspace, event.result.files),
              }))
              break
            case 'integration_started':
              set({ phase: 'integrating', integratorStatus: 'deliberating' })
              break
            case 'integration_result':
              set((state) => ({
                integration: event.result,
                integratorStatus: event.result.status === 'ok' ? 'done' : 'error',
                workspace: mergeFiles(state.workspace, event.result.files),
              }))
              break
            case 'run_closed': {
              const workspace: Record<string, WorkspaceFile> = {}
              for (const file of event.response.workspace) workspace[file.path] = file
              const firstFile =
                event.response.workspace.find((f) => f.path.toLowerCase() === 'readme.md')?.path ??
                event.response.workspace[0]?.path ??
                null
              set({
                phase: event.response.status === 'ok' ? 'closed' : 'error',
                result: event.response,
                error: event.response.error,
                workspace,
                selectedFile: firstFile,
              })
              break
            }
            case 'error':
              set({ phase: 'error', error: event.detail })
              break
            default:
              break
          }
        },
      )
    } catch (err) {
      set({ phase: 'error', error: err instanceof Error ? err.message : String(err) })
    }
  },

  resetRun: () => set({ ...EMPTY_RUN }),

  selectFile: (path) => set({ selectedFile: path }),
  setRepoName: (value) => set({ repoName: value }),
  setRepoPrivate: (value) => set({ repoPrivate: value }),

  exportRun: async () => {
    const { runId, workspace, result, plan, title } = get()
    if (!runId || Object.keys(workspace).length === 0) return
    set({ exportStatus: 'working', exportError: null })
    try {
      const info = await exportWorkspace(runId, Object.values(workspace), {
        run_id: runId,
        title,
        plan,
        agents: result?.agents ?? [],
        integration: result?.integration ?? null,
        trace: result?.trace ?? [],
        totals: result
          ? {
              latency_ms: result.total_latency_ms,
              calls: result.total_calls,
              retries: result.total_retries,
            }
          : null,
      })
      set({ exportStatus: 'done', exportPath: info.path })
    } catch (err) {
      set({ exportStatus: 'error', exportError: err instanceof Error ? err.message : String(err) })
    }
  },

  publishRun: async () => {
    const { runId, repoName, repoPrivate, title, exportStatus } = get()
    if (!runId || !repoName.trim()) return
    if (exportStatus !== 'done') {
      await get().exportRun()
      if (get().exportStatus !== 'done') return
    }
    set({ publishStatus: 'working', publishError: null })
    try {
      const info = await publishWorkspace(runId, repoName.trim(), repoPrivate, `${title} — built by the AI Court Coding Hub`)
      set({ publishStatus: 'done', repoUrl: info.repo_url })
    } catch (err) {
      set({ publishStatus: 'error', publishError: err instanceof Error ? err.message : String(err) })
    }
  },
}))
