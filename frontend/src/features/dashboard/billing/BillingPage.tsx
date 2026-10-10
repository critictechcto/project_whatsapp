import { useEffect, useRef } from 'react'
import { Link, useSearchParams } from 'react-router'
import { buttonClasses, PageHeader, Spinner } from '../../../components/app'
import { useWorkspace } from '../../../lib/workspace'
import { BillingProfileSummary } from './BillingProfileSummary'
import { InvoicesCard } from './InvoicesCard'
import { SubscriptionCard } from './SubscriptionCard'
import { UsageCard } from './UsageCard'
import { useVerifyCashfreeOrder } from './useCheckout'

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
      <CashfreeReturn />
      <SubscriptionCard />
      <div className="grid gap-6 lg:grid-cols-2">
        <UsageCard />
        <BillingProfileSummary />
      </div>
      <InvoicesCard />
    </div>
  )
}

/**
 * Redirect fallback: browsers that can't show Cashfree's modal come back to
 * `billing?cf_order_id=…`. Verify that order once, then drop the parameter.
 */
function CashfreeReturn() {
  const [params, setParams] = useSearchParams()
  const { can } = useWorkspace()
  const { verify, verifying } = useVerifyCashfreeOrder()
  const handled = useRef<string | null>(null)
  const orderId = params.get('cf_order_id')

  useEffect(() => {
    if (!orderId || handled.current === orderId) return
    handled.current = orderId
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        next.delete('cf_order_id')
        return next
      },
      { replace: true },
    )
    // Only the owner may verify; for anyone else the subscription refreshes on its own.
    if (can('owner')) void verify(orderId)
    // verify and can are stable enough for a one-off call keyed on the order id.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId])

  if (!verifying) return null
  return (
    <div role="status" className="flex items-center gap-3 rounded-lg border border-line bg-card px-4 py-3 text-sm text-ink">
      <Spinner size="sm" label="Confirming payment" />
      Confirming your payment with Cashfree…
    </div>
  )
}
