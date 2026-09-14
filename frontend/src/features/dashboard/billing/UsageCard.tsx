import { Link } from 'react-router'
import { Button, Skeleton } from '../../../components/app'
import { useWorkspace } from '../../../lib/workspace'
import { actionErrorMessage } from '../settings/ui/hooks'
import { Meter } from '../settings/ui/Meter'
import { Notice } from '../settings/ui/Notice'
import { SectionCard } from '../settings/ui/SectionCard'
import { usageLabels } from './plans'
import { useUsage } from './queries'

export function UsageCard() {
  const { workspaceId, can } = useWorkspace()
  const usage = useUsage()
  const atLimit = usage.data?.metrics.some((metric) => metric.limit !== null && metric.used >= metric.limit) ?? false

  return (
    <SectionCard id="billing-usage" title="Usage" description="Counted against your plan's limits.">
      {usage.isPending ? (
        <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading usage">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ) : usage.isError ? (
        <Notice
          tone="danger"
          role="alert"
          title="Couldn't load usage"
          action={
            <Button variant="secondary" size="sm" onClick={() => void usage.refetch()}>
              Try again
            </Button>
          }
        >
          {actionErrorMessage(usage.error)}
        </Notice>
      ) : (
        <div className="flex flex-col gap-4">
          {usage.data.metrics.map((metric) => (
            <Meter key={metric.key} label={usageLabels[metric.key] ?? metric.key} used={metric.used} limit={metric.limit} />
          ))}
          {atLimit && (
            <Notice
              tone="warning"
              title="You've reached a plan limit"
              action={
                can('owner') ? (
                  <Link to={`/app/w/${workspaceId}/billing/plans`} className="text-sm font-medium text-accent hover:underline">
                    Compare plans
                  </Link>
                ) : undefined
              }
            >
              Upgrade to add more, or remove something you no longer need.
            </Notice>
          )}
        </div>
      )}
    </SectionCard>
  )
}
