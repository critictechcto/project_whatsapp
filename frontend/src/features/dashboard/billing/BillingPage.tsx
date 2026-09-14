import { Link } from 'react-router'
import { buttonClasses, PageHeader } from '../../../components/app'
import { useWorkspace } from '../../../lib/workspace'
import { BillingProfileSummary } from './BillingProfileSummary'
import { InvoicesCard } from './InvoicesCard'
import { SubscriptionCard } from './SubscriptionCard'
import { UsageCard } from './UsageCard'

export function BillingPage() {
  const { workspaceId, can } = useWorkspace()

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader
        title="Billing"
        description="Your plan, usage, GST details and invoices."
        actions={
          can('owner') && (
            <Link to={`/app/w/${workspaceId}/billing/plans`} className={buttonClasses('secondary', 'md')}>
              See plans
            </Link>
          )
        }
      />
      <SubscriptionCard />
      <div className="grid gap-6 lg:grid-cols-2">
        <UsageCard />
        <BillingProfileSummary />
      </div>
      <InvoicesCard />
    </div>
  )
}
