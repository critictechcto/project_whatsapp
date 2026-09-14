import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, unwrap } from '../../../api/client'
import { Button, Dialog, useToast } from '../../../components/app'
import { site } from '../../../config/site'
import { cn } from '../../../lib/cn'
import { formatDate } from '../../../lib/datetime'
import { useWorkspace } from '../../../lib/workspace'
import { FormError } from '../auth/FormError'
import { actionErrorMessage } from '../settings/ui/hooks'
import type { Subscription } from './plans'
import { billingKeys, subscriptionKey } from './queries'

export function CancelSubscriptionDialog({ subscription, onClose }: { subscription: Subscription; onClose: () => void }) {
  const { workspaceId, timeZone } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [atPeriodEnd, setAtPeriodEnd] = useState(true)
  const periodEnd = formatDate(subscription.current_period_end, timeZone)

  const cancel = useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/billing/subscription/cancel/', { body: { at_period_end: atPeriodEnd } })),
    onSuccess: (updated) => {
      queryClient.setQueryData(subscriptionKey(workspaceId), updated)
      void queryClient.invalidateQueries({ queryKey: billingKeys.all(workspaceId), predicate: (query) => query.queryKey[3] !== 'subscription' })
      toast({
        title: 'Subscription cancelled',
        description: updated.cancel_at_period_end ? `You keep access until ${formatDate(updated.current_period_end, timeZone)}.` : undefined,
        tone: 'success',
      })
      onClose()
    },
  })

  const options = [
    {
      value: true,
      title: 'At the end of the billing period',
      description: `Keep using ${subscription.plan.name} until ${periodEnd}. You won't be charged again.`,
    },
    {
      value: false,
      title: 'Immediately',
      description: `Paid features stop now. For questions about the unused period, email ${site.email.support}.`,
    },
  ]

  return (
    <Dialog
      open
      onOpenChange={(open) => !open && !cancel.isPending && onClose()}
      dismissible={!cancel.isPending}
      size="sm"
      title="Cancel subscription?"
      description="Your workspace, contacts and message history stay in place."
      footer={
        <>
          <Button variant="secondary" disabled={cancel.isPending} onClick={onClose}>
            Keep subscription
          </Button>
          <Button variant="danger" loading={cancel.isPending} onClick={() => cancel.mutate()}>
            Cancel subscription
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <FormError message={cancel.isError ? actionErrorMessage(cancel.error) : undefined} />
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-[13px] font-medium text-ink">When should it end?</legend>
          {options.map((option) => (
            <label
              key={String(option.value)}
              className={cn(
                'flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5',
                atPeriodEnd === option.value ? 'border-accent bg-accent-soft/40' : 'border-line hover:border-ink/20',
              )}
            >
              <input
                type="radio"
                name="cancel-timing"
                checked={atPeriodEnd === option.value}
                onChange={() => setAtPeriodEnd(option.value)}
                className="mt-1 accent-[var(--color-accent)]"
              />
              <span>
                <span className="block text-sm font-medium text-ink">{option.title}</span>
                <span className="block text-[13px] text-muted">{option.description}</span>
              </span>
            </label>
          ))}
        </fieldset>
      </div>
    </Dialog>
  )
}
