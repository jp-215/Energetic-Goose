import { useHubStore } from '../hubStore'
import type { HubRole } from '../types'
import { ModelPicker } from './ModelSelect'

/** Hub role picker bound to the hub store's overrides. */
export default function HubModelSelect({ role }: { role: HubRole }) {
  const override = useHubStore((s) => s.overrides[role])
  const setOverride = useHubStore((s) => s.setOverride)
  const phase = useHubStore((s) => s.phase)
  const locked = phase === 'planning' || phase === 'building' || phase === 'integrating'
  return (
    <ModelPicker
      value={override ?? ''}
      disabled={locked}
      onChange={(m) => setOverride(role, m)}
    />
  )
}
