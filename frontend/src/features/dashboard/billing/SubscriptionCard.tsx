import { useState } from 'react'
import { Link } from 'react-router'
import { Button, buttonClasses, Skeleton, Spinner, StatusBadge } from '../../../components/app'
import { site } from '../../../config/site'
import { formatDate } from '../../../lib/datetime'
import { useWorkspace } from '../../../lib/workspace'
import { actionErrorMessage } from '../settings/ui/hooks'
import { Notice } from '../settings/ui/Notice'
import { SectionCard } from '../settings/ui/SectionCard'
import { CancelSubscriptionDialog } from './CancelSubscriptionDialog'
import { formatPlanPrice } from './money'
import { daysUntil, intervalLabels, isFutureDate, planPricePaise, type Subscription } from './plans'
import { useSubscription } from './queries'

export function SubscriptionCard() {
  const subscription = useSubscription()

  if (subscription.isPending) {
    return (
      <SectionCard id="billing-subscription" title="Current plan">
        <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading your plan">
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-4 w-64" />
        </div>
      </SectionCard>
    )
  }

  if (subscription.isError) {
    return (
      <Notice
        tone="danger"
        role="alert"
        title="Couldn't load your plan"
        action={
          <Button variant="secondary" size="sm" onClick={() => void subscription.refetch()}>
            Try again
          </Button>
        }
      >
        {actionErrorMessage(subscription.error)}
      </Notice>
    )
  }

  return <SubscriptionDetails subscription={subscription.data} />
}

function SubscriptionDetails({ subscription }: { subscription: Subscription }) {
  const { workspaceId, timeZone, can } = useWorkspace()
  const isOwner = can('owner')
  const [cancelOpen, setCancelOpen] = useState(false)
  const { plan, status, interval } = subscription
  const trialDays = daysUntil(subscription.trial_ends_at)
  const periodEnd = formatDate(subscription.current_period_end, timeZone)
  const canCancel = isOwner && (status === 'active' || status === 'halted') && !subscription.cancel_at_period_end
  const isPaid = status === 'active' || status === 'halted' || (status === 'cancelled' && isFutureDate(subscription.current_period_end))

  return (
    <SectionCard
      id="billing-subscription"
      title="Current plan"
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={status} />
          {subscription.cancel_at_period_end && status === 'active' && <StatusBadge tone="amber">Cancels {periodEnd}</StatusBadge>}
        </div>
      }
      footer={
        isOwner ? (
          <>
            {canCancel && (
              <Button variant="ghost" onClick={() => setCancelOpen(true)}>
                Cancel subscription
              </Button>
            )}
            <Link to={`/app/w/${workspaceId}/billing/plans?interval=${interval}`} className={buttonClasses(status === 'active' ? 'secondary' : 'primary', 'md')}>
              {status === 'active' ? 'Change plan' : 'Choose a plan'}
            </Link>
          </>
        ) : (
          <p className="text-[13px] text-muted">Only the workspace owner can change the plan or cancel.</p>
        )
      }
    >
      <div className="flex flex-col gap-4">
        <div>
          <p className="font-display text-xl font-semibold tracking-[-0.01em] text-ink">{plan.name}</p>
          <p className="text-sm text-muted">
            {status === 'trialing'
              ? `Free trial of the ${plan.name} plan`
              : `${formatPlanPrice(planPricePaise(plan, interval))} / ${interval === 'annual' ? 'year' : 'month'} + ${site.gstRate}% GST`}
          </p>
        </div>

        {status === 'trialing' && trialDays !== null && (
          <Notice tone={trialDays <= 3 ? 'warning' : 'info'} title={trialDays === 0 ? 'Your trial ends today' : `${trialDays} ${trialDays === 1 ? 'day' : 'days'} left in your trial`}>
            The trial ends on {formatDate(subscription.trial_ends_at, timeZone)}. Choose a plan before then to keep using {site.name}{' '}
            without a break.
          </Notice>
        )}
        {status === 'pending' && (
          <div role="status" className="flex items-start gap-3 rounded-lg border border-line bg-paper px-4 py-3 text-sm">
            <Spinner size="sm" label="Confirming payment" />
            <div>
              <p className="font-medium text-ink">Confirming your payment…</p>
              <p className="text-[13px] text-muted">Razorpay is confirming the payment. This usually takes under a minute and this page updates on its own.</p>
            </div>
          </div>
        )}
        {status === 'active' && (
          <p className="text-sm text-ink-2">
            {subscription.cancel_at_period_end
              ? `Your subscription ends on ${periodEnd}. You keep access until then.`
              : `Renews automatically on ${periodEnd}.`}
          </p>
        )}
        {status === 'halted' && (
          <Notice tone="danger" title="Razorpay couldn't collect your last payment">
            Razorpay may retry the charge. Check the payment method on your mandate, or choose a plan again to pay now. Contact{' '}
            {site.email.support} if you need help.
          </Notice>
        )}
        {status === 'cancelled' && (
          <Notice tone="warning" title="Subscription cancelled">
            {isFutureDate(subscription.current_period_end)
              ? `You keep access until ${periodEnd}. Choose a plan to subscribe again.`
              : 'Choose a plan to subscribe again.'}
          </Notice>
        )}
        {status === 'expired' && (
          <Notice tone="warning" title={subscription.trial_ends_at && !subscription.current_period_end ? 'Your trial has ended' : 'Your plan has expired'}>
            Choose a plan to continue using {site.name}.
          </Notice>
        )}

        {isPaid && (
          <dl className="grid gap-x-6 gap-y-2 border-t border-line-2 pt-4 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-[12.5px] text-muted">Billing cycle</dt>
              <dd className="text-ink">{intervalLabels[interval]}</dd>
            </div>
            <div>
              <dt className="text-[12.5px] text-muted">Current period</dt>
              <dd className="text-ink">
                {formatDate(subscription.current_period_start, timeZone)} – {periodEnd}
              </dd>
            </div>
            <div>
              <dt className="text-[12.5px] text-muted">Payments</dt>
              <dd className="text-ink">Razorpay</dd>
            </div>
          </dl>
        )}
      </div>

      {cancelOpen && <CancelSubscriptionDialog subscription={subscription} onClose={() => setCancelOpen(false)} />}
    </SectionCard>
  )
}
