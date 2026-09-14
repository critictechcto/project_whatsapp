import { ArrowLeft, Check } from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Button, PageHeader, Skeleton, Spinner, StatusBadge } from '../../../components/app'
import { ANNUAL_MONTHS_CHARGED, site } from '../../../config/site'
import { cn } from '../../../lib/cn'
import { useWorkspace } from '../../../lib/workspace'
import { actionErrorMessage } from '../settings/ui/hooks'
import { Notice } from '../settings/ui/Notice'
import { SegmentedControl } from '../settings/ui/SegmentedControl'
import { formatPlanPrice } from './money'
import { freeMonthsLabel, intervalLabels, limitLabel, planCopy, planPricePaise, type BillingInterval, type Plan } from './plans'
import { usePlans, useSubscription } from './queries'
import { checkoutStageText, useCheckout } from './useCheckout'

export function PlansPage() {
  const { workspaceId, can } = useWorkspace()
  const isOwner = can('owner')
  const [params] = useSearchParams()
  const [interval, setBillingInterval] = useState<BillingInterval>(params.get('interval') === 'annual' ? 'annual' : 'monthly')
  const plans = usePlans()
  const subscription = useSubscription()
  const { checkout, stage, planId } = useCheckout()
  const resumePlan = params.get('resume') === '1' ? plans.data?.find((plan) => plan.id === params.get('plan')) : undefined

  const isCurrent = (plan: Plan) =>
    subscription.data?.plan.id === plan.id &&
    subscription.data.interval === interval &&
    (subscription.data.status === 'active' || subscription.data.status === 'pending')

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader
        eyebrow={
          <Link to={`/app/w/${workspaceId}/billing`} className="inline-flex items-center gap-1 hover:text-ink">
            <ArrowLeft className="size-3" aria-hidden="true" /> Billing
          </Link>
        }
        title="Plans"
        description={`Prices are in rupees and don't include ${site.gstRate}% GST. Annual billing charges ${ANNUAL_MONTHS_CHARGED} months for a full year.`}
      />

      {!isOwner && (
        <Notice title="View only">Only the workspace owner can choose or change the plan.</Notice>
      )}

      {isOwner && resumePlan && stage === 'idle' && (
        <Notice
          tone="success"
          title="Billing details saved"
          action={<Button onClick={() => void checkout(resumePlan, interval)}>Continue to payment</Button>}
        >
          Continue to pay for the {resumePlan.name} plan, billed {intervalLabels[interval].toLowerCase()}.
        </Notice>
      )}

      {stage !== 'idle' && (
        <div role="status" className="flex items-center gap-3 rounded-lg border border-line bg-card px-4 py-3 text-sm text-ink">
          <Spinner size="sm" label="Checkout in progress" />
          {checkoutStageText[stage]}
        </div>
      )}

      <SegmentedControl
        label="Billing cycle"
        value={interval}
        onValueChange={setBillingInterval}
        options={[
          { value: 'monthly', label: 'Monthly' },
          { value: 'annual', label: 'Annual', hint: freeMonthsLabel },
        ]}
      />

      {plans.isPending ? (
        <div className="grid gap-4 md:grid-cols-3" aria-busy="true" aria-label="Loading plans">
          {[0, 1, 2].map((index) => (
            <Skeleton key={index} className="h-80 w-full rounded-xl" />
          ))}
        </div>
      ) : plans.isError ? (
        <Notice
          tone="danger"
          role="alert"
          title="Couldn't load plans"
          action={
            <Button variant="secondary" size="sm" onClick={() => void plans.refetch()}>
              Try again
            </Button>
          }
        >
          {actionErrorMessage(plans.error)}
        </Notice>
      ) : (
        <ul className="grid gap-4 md:grid-cols-3">
          {plans.data.map((plan) => {
            const copy = planCopy(plan.id)
            const price = planPricePaise(plan, interval)
            const current = isCurrent(plan)
            return (
              <li
                key={plan.id}
                className={cn('flex flex-col rounded-xl border bg-card p-5', copy?.recommended ? 'border-accent' : 'border-line')}
              >
                <div className="flex items-center justify-between gap-2">
                  <h2 className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">{plan.name}</h2>
                  {current ? <StatusBadge tone="green">Current plan</StatusBadge> : copy?.recommended && <StatusBadge tone="blue">Recommended</StatusBadge>}
                </div>
                {copy?.blurb && <p className="mt-1 text-[13px] text-muted">{copy.blurb}</p>}
                <p className="mt-4">
                  <span className="font-display text-3xl font-semibold tracking-[-0.02em] text-ink">{formatPlanPrice(price)}</span>
                  <span className="text-sm text-muted"> / {interval === 'annual' ? 'year' : 'month'}</span>
                </p>
                <p className="text-[13px] text-muted">
                  + {site.gstRate}% GST
                  {interval === 'annual' && ` · works out to ${formatPlanPrice(Math.round(price / 12))} a month`}
                </p>
                <ul className="mt-4 flex flex-col gap-1.5 border-t border-line-2 pt-4 text-sm">
                  {(['whatsapp_numbers', 'members', 'contacts'] as const).map((key) => (
                    <li key={key} className="font-medium text-ink">
                      {limitLabel(key, plan.limits[key])}
                    </li>
                  ))}
                </ul>
                <ul className="mt-3 flex flex-1 flex-col gap-1.5 text-[13px] text-ink-2">
                  {plan.features.map((feature) => (
                    <li key={feature} className="flex gap-2">
                      <Check className="mt-0.5 size-3.5 shrink-0 text-accent" aria-hidden="true" />
                      {feature}
                    </li>
                  ))}
                </ul>
                {isOwner && (
                  <Button
                    className="mt-5 w-full"
                    variant={copy?.recommended ? 'primary' : 'secondary'}
                    disabled={current || stage !== 'idle'}
                    loading={planId === plan.id}
                    onClick={() => void checkout(plan, interval)}
                  >
                    {current ? 'Current plan' : `Choose ${plan.name}`}
                  </Button>
                )}
              </li>
            )
          })}
        </ul>
      )}

      <p className="text-[13px] text-muted">
        Payments are processed by Razorpay as a recurring subscription. Available payment methods depend on what Razorpay
        supports for recurring payments. Meta's WhatsApp message charges, where they apply, are billed separately by Meta.
      </p>
    </div>
  )
}
