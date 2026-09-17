import { ChartColumn } from 'lucide-react'
import { Link } from 'react-router'
import { buttonClasses } from '../../../../components/app'
import { plans } from '../../../../config/site'
import { useWorkspace } from '../../../../lib/workspace'

/** First plan that lists analytics (Growth); later plans include everything before them. */
const analyticsPlan = plans.find((plan) => plan.features.some((feature) => /analytics/i.test(feature)))

/** Shown instead of the reports when the plan lacks the `analytics` feature (409 `feature_not_available`). */
export function UpgradePanel() {
  const { workspaceId, can } = useWorkspace()
  return (
    <section
      aria-labelledby="analytics-upgrade-title"
      className="flex flex-col items-start gap-4 rounded-xl border border-line bg-card p-6 sm:flex-row sm:items-center sm:p-8"
    >
      <div aria-hidden="true" className="grid size-11 shrink-0 place-items-center rounded-lg border border-line bg-paper text-accent-2">
        <ChartColumn className="size-5" />
      </div>
      <div className="min-w-0 flex-1">
        <h2 id="analytics-upgrade-title" className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">
          {analyticsPlan ? `Analytics is included in the ${analyticsPlan.name} plan and above` : 'Analytics is not included in your plan'}
        </h2>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          See delivery, read and reply rates across campaigns, templates and your team, with CSV exports. Your current plan doesn&apos;t
          include analytics.
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
