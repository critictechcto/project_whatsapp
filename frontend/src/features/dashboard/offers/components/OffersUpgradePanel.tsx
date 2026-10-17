import { TicketPercent } from 'lucide-react'
import { Link } from 'react-router'
import { buttonClasses } from '../../../../components/app'
import { useWorkspace } from '../../../../lib/workspace'

/** Shown instead of offers when the plan lacks selling on WhatsApp (409 `feature_not_available`). */
export function OffersUpgradePanel() {
  const { workspaceId, can } = useWorkspace()
  return (
    <section
      aria-labelledby="offers-upgrade-title"
      className="flex flex-col items-start gap-4 rounded-xl border border-line bg-card p-6 sm:flex-row sm:items-center sm:p-8"
    >
      <div aria-hidden="true" className="grid size-11 shrink-0 place-items-center rounded-lg border border-line bg-paper text-accent-2">
        <TicketPercent className="size-5" />
      </div>
      <div className="min-w-0 flex-1">
        <h2 id="offers-upgrade-title" className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">
          Offer codes come with selling on WhatsApp
        </h2>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Customers send a code like DIWALI, get your offer and the discount at checkout or at your counter. Your current plan doesn&apos;t include
          selling on WhatsApp.
        </p>
        {!can('admin') && <p className="mt-2 text-sm text-muted">Ask a workspace owner or admin to change the plan.</p>}
      </div>
      {can('admin') && (
        <Link to={`/app/w/${workspaceId}/billing/plans`} className={buttonClasses('primary', 'md', 'w-full sm:w-auto')}>
          Compare plans
        </Link>
      )}
    </section>
  )
}
