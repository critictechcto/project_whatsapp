import { Check, ChevronsUpDown, Plus } from 'lucide-react'
import { useNavigate } from 'react-router'
import { DropdownMenu, type MenuEntry } from '../../../components/app'
import { roleLabels } from '../../../lib/roles'
import { useWorkspace } from '../../../lib/workspace'
import { useMe } from '../auth/session'

export function WorkspaceSwitcher({ onNavigate }: { onNavigate?: () => void }) {
  const { workspace, role } = useWorkspace()
  const me = useMe()
  const navigate = useNavigate()

  const go = (to: string) => {
    onNavigate?.()
    navigate(to)
  }

  const items: MenuEntry[] = [
    { type: 'label', id: 'label', label: 'Workspaces' },
    ...(me.data?.memberships ?? []).map(
      (membership): MenuEntry => ({
        id: membership.workspace_id,
        label: membership.workspace_name,
        icon: membership.workspace_id === workspace.id ? <Check /> : <span className="size-4" />,
        onSelect: () => go(`/app/w/${membership.workspace_id}`),
      }),
    ),
    { type: 'separator', id: 'sep' },
    { id: 'create', label: 'Create workspace', icon: <Plus />, onSelect: () => go('/app/workspaces/new') },
  ]

  return (
    <DropdownMenu
      placement="bottom-start"
      triggerVariant="ghost"
      triggerClassName="h-auto w-full justify-between gap-2 border border-line bg-card px-2.5 py-2 text-left hover:bg-paper"
      menuClassName="w-60"
      trigger={
        <>
          <span className="min-w-0">
            <span className="sr-only">Current workspace: </span>
            <span className="block truncate text-sm font-medium text-ink">{workspace.name}</span>
            <span className="block font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted">{roleLabels[role]}</span>
          </span>
          <ChevronsUpDown className="size-4 shrink-0 text-muted" aria-hidden="true" />
        </>
      }
      items={items}
    />
  )
}
