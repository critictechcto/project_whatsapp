import { ArrowLeft, Check } from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Button, PageHeader, Skeleton, Spinner, StatusBadge } from '../../../components/app'
import { cn } from '../../../lib/cn'
import { useWorkspace } from '../../../lib/workspace'
import { actionErrorMessage } from '../settings/ui/hooks'
import { Notice } from '../settings/ui/Notice'
import { SegmentedControl } from '../settings/ui/SegmentedControl'
import { formatPlanPrice, gstRateOf } from './money'
import { freeMonthsLabel, intervalLabels, limitLabel, planCopy, planPricePaise, type BillingInterval, type Plan } from './plans'
import { usePlans, useSubscription } from './queries'
import { checkoutStageText, isPaymentMode, useCheckout, type PaymentMode } from './useCheckout'

export function PlansPage() {
  const { workspaceId, can } = useWorkspace()
  const isOwner = can('owner')
  const [params] = useSearchParams()
  const [interval, setBillingInterval] = useState<BillingInterval>(params.get('interval') === 'annual' ? 'annual' : 'monthly')
  const plans = usePlans()
  const subscription = useSubscription()
  const { checkout, stage, planId, provider } = useCheckout()
  const resumePlan = params.get('resume') === '1' ? plans.data?.find((plan) => plan.id === params.get('plan')) : undefined

  const requestedMode = params.get('payment_mode')
  const [paymentMode, setPaymentMode] = useState<PaymentMode>(isPaymentMode(requestedMode) ? requestedMode : 'autopay')

  const isCurrent = (plan: Plan) =>
    subscription.data?.plan.id === plan.id &&
    subscription.data.interval === interval &&
    (subscription.data.status === 'active' || subscription.data.status === 'pending')
  const checkoutProvider = subscription.data?.checkout_provider
  // Razorpay offers auto-pay or paying once; Cashfree checkouts are always paid once.
  const razorpay = checkoutProvider === 'razorpay'
  const active = subscription.data?.status === 'active'
  // A one-time (prepaid) plan is renewed or changed by paying once again, so its current plan stays choosable.
  const prepaidActive = active && subscription.data?.payment_mode === 'one_time'
  const autopayActive = active && subscription.data?.payment_mode === 'autopay'
  // The server refuses switching between auto-pay and paying once while a paid period runs.
  const switchBlocked = razorpay && ((paymentMode === 'autopay' && prepaidActive) || (paymentMode === 'one_time' && autopayActive))
  const renewable = prepaidActive && (!razorpay || paymentMode === 'one_time')
  const checkoutMode = razorpay ? paymentMode : undefined
  const gstRate = gstRateOf(subscription.data)
  const monthlyNote = (price: number) => `works out to ${formatPlanPrice(Math.round(price / 12))} a month`
  // The toggle's "N months free" follows the recommended plan's own two prices; left out when unknown.
  const hintPlan = plans.data?.find((plan) => planCopy(plan.id)?.recommended) ?? plans.data?.[0]
  const annualHint = hintPlan ? freeMonthsLabel(hintPlan) : null

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader
        eyebrow={
          <Link to={`/app/w/${workspaceId}/billing`} className="inline-flex items-center gap-1 hover:text-ink">
            <ArrowLeft className="size-3" aria-hidden="true" /> Billing
          </Link>
        }
        title="Plans"
        description={`${gstRate > 0 ? `Prices are in rupees and don't include ${gstRate}% GST.` : 'Prices are in rupees, with no GST added.'} Annual plans are paid for a year in advance.`}
      />

      {!isOwner && (
        <Notice title="View only">Only the workspace owner can choose or change the plan.</Notice>
      )}

      {isOwner && resumePlan && stage === 'idle' && (
        <Notice
          tone="success"
          title="Billing details saved"
          action={
            <Button
              disabled={planPricePaise(resumePlan, interval) === null}
              onClick={() => void checkout(resumePlan, interval, checkoutMode)}
            >
              Continue to payment
            </Button>
          }
        >
          Continue to pay for the {resumePlan.name} plan, billed {intervalLabels[interval].toLowerCase()}.
        </Notice>
      )}

      {stage !== 'idle' && (
        <div role="status" className="flex items-center gap-3 rounded-lg border border-line bg-card px-4 py-3 text-sm text-ink">
          <Spinner size="sm" label="Checkout in progress" />
          {checkoutStageText(stage, provider)}
        </div>
      )}

      {isOwner && renewable && (
        <Notice tone="warning" title="Your current plan is still active">
          Your new plan starts now. Unused days on the current plan aren't refunded. Renewing the same plan and billing cycle
          adds the new period after the current one ends.
        </Notice>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl
          label="Billing cycle"
          value={interval}
          onValueChange={setBillingInterval}
          options={[
            { value: 'monthly', label: 'Monthly' },
            { value: 'annual', label: 'Annual', hint: annualHint ?? undefined },
          ]}
        />
        {razorpay && (
          <SegmentedControl
            label="How to pay"
            value={paymentMode}
            onValueChange={setPaymentMode}
            options={[
              { value: 'autopay', label: 'Auto-pay' },
              { value: 'one_time', label: 'Pay once' },
            ]}
          />
        )}
      </div>

      {isOwner && switchBlocked && (
        <Notice title={paymentMode === 'autopay' ? 'Your plan is paid for this period' : 'Your plan renews by auto-pay'}>
          {paymentMode === 'autopay'
            ? 'You can switch to auto-pay when your paid period ends.'
            : 'To pay once instead, cancel auto-pay. You can pay once after the current period ends.'}
        </Notice>
      )}

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
                {price === null ? (
                  <>
                    <p className="mt-4 font-display text-3xl font-semibold tracking-[-0.02em] text-muted">Not available</p>
                    <p className="text-[13px] text-muted">
                      {interval === 'annual' ? 'Annual' : 'Monthly'} billing can't be bought right now.
                    </p>
                  </>
                ) : (
                  <>
                    <p className="mt-4">
                      <span className="font-display text-3xl font-semibold tracking-[-0.02em] text-ink">{formatPlanPrice(price)}</span>
                      <span className="text-sm text-muted"> / {interval === 'annual' ? 'year' : 'month'}</span>
                    </p>
                    {(gstRate > 0 || interval === 'annual') && (
                      <p className="text-[13px] text-muted">
                        {[
                          gstRate > 0 && `+ ${gstRate}% GST`,
                          interval === 'annual' && monthlyNote(price),
                          interval === 'annual' && freeMonthsLabel(plan),
                        ]
                          .filter(Boolean)
                          .join(' · ')}
                      </p>
                    )}
                  </>
                )}
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
                    disabled={price === null || switchBlocked || (current && !renewable) || stage !== 'idle'}
                    loading={planId === plan.id}
                    onClick={() => void checkout(plan, interval, checkoutMode)}
                  >
                    {current ? (renewable ? `Renew ${plan.name}` : 'Current plan') : `Choose ${plan.name}`}
                  </Button>
                )}
              </li>
            )
          })}
        </ul>
      )}

      <p className="text-[13px] text-muted">
        {checkoutProvider === 'cashfree'
          ? "Payments are processed by Cashfree. You pay for a month or a year at a time; nothing is charged automatically. We'll email you before your plan ends."
          : paymentMode === 'one_time'
            ? "Payments are processed by Razorpay. Pay for a month or a year at a time; nothing is charged automatically. We'll email you before your plan ends."
            : 'Payments are processed by Razorpay. Charged automatically each month or year by UPI AutoPay or card. Cancel anytime.'}{' '}
        Meta's WhatsApp message charges, where they apply, are billed separately by Meta.
      </p>
    </div>
  )
}
