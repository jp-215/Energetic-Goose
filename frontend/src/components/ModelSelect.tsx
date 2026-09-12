import { useCourtStore } from '../store'
import type { Role } from '../types'

/** Model picker that loads the platform's model list on first interaction —
 * never as a page-load precondition. */
export default function ModelSelect({ role }: { role: Role }) {
  const models = useCourtStore((s) => s.models)
  const modelsLoading = useCourtStore((s) => s.modelsLoading)
  const override = useCourtStore((s) => s.overrides[role])
  const setOverride = useCourtStore((s) => s.setOverride)
  const ensureModels = useCourtStore((s) => s.ensureModels)

  return (
    <select
      className="nodrag field-input"
      value={override ?? ''}
      onPointerDown={ensureModels}
      onFocus={ensureModels}
      onChange={(e) => setOverride(role, e.target.value)}
    >
      <option value="">
        {modelsLoading ? 'loading platform models…' : 'platform default'}
      </option>
      {models.map((m) => (
        <option key={m} value={m}>
          {m}
        </option>
      ))}
    </select>
  )
}
