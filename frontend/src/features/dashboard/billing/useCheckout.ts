import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { api, unwrap } from '../../../api/client'
import { isApiError } from '../../../api/errors'
import { useToast } from '../../../components/app'
import { CheckoutDismissed, openRazorpayCheckout } from '../../../lib/integrations/razorpay'
import { useWorkspace } from '../../../lib/workspace'
import { actionErrorMessage } from '../settings/ui/hooks'
import type { BillingInterval, Plan } from './plans'
import { billingKeys, subscriptionKey } from './queries'

export type CheckoutStage = 'idle' | 'creating' | 'paying' | 'verifying'

export const checkoutStageText: Record<Exclude<CheckoutStage, 'idle'>, string> = {
  creating: 'Starting checkout…',
  paying: 'Complete the payment in the Razorpay window.',
  verifying: 'Confirming your payment…',
}

/**
 * checkout → Razorpay Checkout → verify. A missing billing profile sends the owner to the
 * billing details form, which returns to the plans page to resume.
 */
export function useCheckout() {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { toast } = useToast()
  const [stage, setStage] = useState<CheckoutStage>('idle')
  const [planId, setPlanId] = useState<string | null>(null)

  async function checkout(plan: Plan, interval: BillingInterval) {
    setStage('creating')
    setPlanId(plan.id)
    try {
      const session = await unwrap(api.POST('/api/v1/billing/subscription/checkout/', { body: { plan_id: plan.id, interval } }))
      setStage('paying')
      const payment = await openRazorpayCheckout(session)
      setStage('verifying')
      const subscription = await unwrap(api.POST('/api/v1/billing/subscription/verify/', { body: payment }))
      queryClient.setQueryData(subscriptionKey(workspaceId), subscription)
      void queryClient.invalidateQueries({
        queryKey: billingKeys.all(workspaceId),
        predicate: (query) => query.queryKey[3] !== 'subscription',
      })
      toast(
        subscription.status === 'active'
          ? { title: `You're on the ${plan.name} plan`, tone: 'success' }
          : { title: 'Payment received', description: "We're confirming it with Razorpay. Your plan updates here shortly.", tone: 'info' },
      )
      navigate(`/app/w/${workspaceId}/billing`)
    } catch (error) {
      if (isApiError(error, 'billing_profile_required')) {
        toast({ title: 'Add your billing details first', description: 'Invoices need your legal name, address and GSTIN if you have one.', tone: 'info' })
        const params = new URLSearchParams({ next: 'plans', plan: plan.id, interval })
        navigate(`/app/w/${workspaceId}/billing/profile?${params}`)
      } else if (error instanceof CheckoutDismissed) {
        toast({ title: 'Payment not completed', description: 'The Razorpay window was closed before paying.', tone: 'info' })
      } else {
        toast({ title: "Payment didn't go through", description: actionErrorMessage(error), tone: 'error' })
      }
    } finally {
      setStage('idle')
      setPlanId(null)
    }
  }

  return { checkout, stage, planId }
}
