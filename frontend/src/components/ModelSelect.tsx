import { useCourtStore } from '../store'
import type { Role } from '../types'

/** Presentational model picker. Loads the platform's model list on first
 * interaction — never as a page-load precondition. */
export function ModelPicker({
  value,
  onChange,
  disabled,
}: {
  value: string
  onChange: (model: string) => void
  disabled?: boolean
}) {
  const models = useCourtStore((s) => s.models)
  const modelsLoading = useCourtStore((s) => s.modelsLoading)
  const ensureModels = useCourtStore((s) => s.ensureModels)

  return (
    <select
      className="nodrag field-input"
      value={value}
      disabled={disabled}
      onPointerDown={ensureModels}
      onFocus={ensureModels}
      onChange={(e) => onChange(e.target.value)}
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

/** Court role picker bound to the court store's overrides. */
export default function ModelSelect({ role }: { role: Role }) {
  const override = useCourtStore((s) => s.overrides[role])
  const setOverride = useCourtStore((s) => s.setOverride)
  return <ModelPicker value={override ?? ''} onChange={(m) => setOverride(role, m)} />
}
