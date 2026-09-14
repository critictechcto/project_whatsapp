import { ShieldAlert } from 'lucide-react'
import { Link } from 'react-router'
import { buttonClasses } from '../../../../components/app'
import { useWorkspace } from '../../../../lib/workspace'

/** Shown for `catalog_permissions_missing`: the seller must reconnect WhatsApp and allow catalog access. */
export function PermissionsNotice() {
  const { workspaceId } = useWorkspace()
  return (
    <div role="alert" className="flex flex-col gap-3 rounded-lg border border-signal/25 bg-signal-soft/50 p-4 sm:flex-row sm:items-start">
      <ShieldAlert className="size-5 shrink-0 text-signal" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-ink">Reconnect WhatsApp to allow catalog access</p>
        <p className="mt-1 text-[13px] text-ink-2">
          Your WhatsApp connection doesn&apos;t include Meta&apos;s catalog permissions. Reconnect WhatsApp and approve catalog
          management when Meta asks, then come back here.
        </p>
      </div>
      <Link to={`/app/w/${workspaceId}/whatsapp`} className={buttonClasses('secondary', 'sm')}>
        Go to WhatsApp
      </Link>
    </div>
  )
}
