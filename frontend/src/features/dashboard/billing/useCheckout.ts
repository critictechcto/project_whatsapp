import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { api, unwrap } from '../../../api/client'
import { isApiError } from '../../../api/errors'
import type { Schemas } from '../../../api/types'
import { useToast } from '../../../components/app'
import { formatDate } from '../../../lib/datetime'
import { openCashfreeCheckout } from '../../../lib/integrations/cashfree'
import { CheckoutDismissed, openRazorpayCheckout } from '../../../lib/integrations/razorpay'
import { useWorkspace } from '../../../lib/workspace'
import { actionErrorMessage } from '../settings/ui/hooks'
import type { BillingInterval, Plan, Subscription } from './plans'
import { billingKeys, subscriptionKey } from './queries'

export type CheckoutStage = 'idle' | 'creating' | 'paying' | 'verifying'
export type BillingProvider = Schemas['PaymentProviderEnum']

export const providerNames: Record<BillingProvider, string> = { razorpay: 'Razorpay', cashfree: 'Cashfree' }

export function checkoutStageText(stage: Exclude<CheckoutStage, 'idle'>, provider: BillingProvider = 'razorpay'): string {
  switch (stage) {
    case 'creating':
      return 'Starting checkout…'
    case 'paying':
      return `Complete the payment in the ${providerNames[provider]} window.`
    case 'verifying':
      return 'Confirming your payment…'
  }
}

/** Toasts for a verify call's outcome; shared by checkout and the `?cf_order_id=` return. */
function useVerifyFeedback() {
  const { workspaceId, timeZone } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()

  function applied(subscription: Subscription, previous: Subscription | undefined) {
    queryClient.setQueryData(subscriptionKey(workspaceId), subscription)
    void queryClient.invalidateQueries({
      queryKey: billingKeys.all(workspaceId),
      predicate: (query) => query.queryKey[3] !== 'subscription',
    })
    const renewed =
      previous?.status === 'active' && previous.plan.id === subscription.plan.id && previous.interval === subscription.interval
    if (subscription.status !== 'active') {
      const provider = providerNames[subscription.provider ?? 'razorpay']
      toast({ title: 'Payment received', description: `We're confirming it with ${provider}. Your plan updates here shortly.`, tone: 'info' })
    } else if (renewed && subscription.provider === 'cashfree') {
      toast({
        title: 'Payment received',
        description: `Your ${subscription.plan.name} plan is paid until ${formatDate(subscription.current_period_end, timeZone)}.`,
        tone: 'success',
      })
    } else {
      toast({ title: `You're on the ${subscription.plan.name} plan`, tone: 'success' })
    }
  }

  /** True when the error was a verify outcome this handled. */
  function failed(error: unknown): boolean {
    if (isApiError(error, 'payment_not_completed')) {
      toast({ title: 'Payment not completed', description: "You haven't been charged.", tone: 'info' })
      return true
    }
    return false
  }

  return { applied, failed }
}

/**
 * checkout → Razorpay or Cashfree Checkout → verify. A missing billing profile sends the owner to the
 * billing details form, which returns to the plans page to resume. For Cashfree, verify always runs
 * after the window closes: the server asks Cashfree whether the order was paid.
 */
export function useCheckout() {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { toast } = useToast()
  const feedback = useVerifyFeedback()
  const [stage, setStage] = useState<CheckoutStage>('idle')
  const [planId, setPlanId] = useState<string | null>(null)
  const [provider, setProvider] = useState<BillingProvider>('razorpay')

  async function checkout(plan: Plan, interval: BillingInterval) {
    setStage('creating')
    setPlanId(plan.id)
    const previous = queryClient.getQueryData<Subscription>(subscriptionKey(workspaceId))
    let sessionProvider: BillingProvider = previous?.checkout_provider ?? 'razorpay'
    setProvider(sessionProvider)
    try {
      const session = await unwrap(api.POST('/api/v1/billing/subscription/checkout/', { body: { plan_id: plan.id, interval } }))
      sessionProvider = session.provider === 'cashfree' ? 'cashfree' : 'razorpay'
      setProvider(sessionProvider)
      setStage('paying')
      let body: Schemas['CheckoutVerifyRequest']
      if (sessionProvider === 'cashfree') {
        const outcome = await openCashfreeCheckout(session)
        // The browser is leaving for the return URL; the billing page verifies when it comes back.
        if (outcome === 'redirecting') return
        body = { order_id: session.order_id ?? '' }
      } else {
        body = await openRazorpayCheckout(session)
      }
      setStage('verifying')
      const subscription = await unwrap(api.POST('/api/v1/billing/subscription/verify/', { body }))
      feedback.applied(subscription, previous)
      navigate(`/app/w/${workspaceId}/billing`)
    } catch (error) {
      if (isApiError(error, 'billing_profile_required')) {
        toast({
          title: 'Add your billing details first',
          description: 'Invoices need your legal name, address and GSTIN if you have one. Cashfree also needs a phone number.',
          tone: 'info',
        })
        const params = new URLSearchParams({ next: 'plans', plan: plan.id, interval })
        navigate(`/app/w/${workspaceId}/billing/profile?${params}`)
      } else if (error instanceof CheckoutDismissed) {
        toast({ title: 'Payment not completed', description: 'The Razorpay window was closed before paying.', tone: 'info' })
      } else if (!feedback.failed(error)) {
        toast({ title: "Payment didn't go through", description: actionErrorMessage(error), tone: 'error' })
      }
    } finally {
      setStage('idle')
      setPlanId(null)
    }
  }

  return { checkout, stage, planId, provider }
}

/** Verifies a Cashfree order after the browser comes back from Cashfree's return URL. */
export function useVerifyCashfreeOrder() {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const feedback = useVerifyFeedback()
  const [verifying, setVerifying] = useState(false)

  async function verify(orderId: string) {
    setVerifying(true)
    const previous = queryClient.getQueryData<Subscription>(subscriptionKey(workspaceId))
    try {
      const subscription = await unwrap(api.POST('/api/v1/billing/subscription/verify/', { body: { order_id: orderId } }))
      feedback.applied(subscription, previous)
    } catch (error) {
      if (!feedback.failed(error)) {
        toast({ title: "We couldn't confirm this payment", description: actionErrorMessage(error), tone: 'error' })
      }
    } finally {
      setVerifying(false)
    }
  }

  return { verify, verifying }
}
