import { zodResolver } from '@hookform/resolvers/zod'
import { useId } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'
import { applyApiErrorToForm, isApiError } from '../../../../api/errors'
import { Button, Checkbox, Dialog, Field, Textarea } from '../../../../components/app'
import { orderMutations, type Order } from '../api'
import { Notice } from './Notice'

const MAX_REASON = 200

const schema = z.object({
  reason: z.string().trim().max(MAX_REASON, `Keep the reason under ${MAX_REASON} characters.`),
  restock: z.boolean(),
  notify_buyer: z.boolean(),
})

type FormValues = z.infer<typeof schema>

type CancelDialogProps = {
  order: Order
  onClose: () => void
  onCancelled: (order: Order) => void
  onFailed: (error: unknown) => void
}

/** Mount it only while open, so every opening starts with a fresh form. */
export function CancelDialog({ order, onClose, onCancelled, onFailed }: CancelDialogProps) {
  const formId = useId()
  const {
    register,
    handleSubmit,
    setError,
    control,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { reason: '', restock: true, notify_buyer: true },
  })
  const reasonLength = useWatch({ control, name: 'reason' }).length

  const onSubmit = handleSubmit(async (values) => {
    try {
      onCancelled(await orderMutations.cancel(order.id, values))
    } catch (error) {
      if (isApiError(error, 'invalid')) {
        applyApiErrorToForm(error, setError, { fields: ['reason', 'restock', 'notify_buyer'] })
        return
      }
      onFailed(error)
    }
  })

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
      dismissible={!isSubmitting}
      title={`Cancel ${order.number}?`}
      description="If a payment link is still open, it's cancelled too so the buyer can't pay for this order."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
            Keep order
          </Button>
          <Button type="submit" form={formId} variant="danger" loading={isSubmitting}>
            Cancel order
          </Button>
        </>
      }
    >
      <form id={formId} onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        {errors.root?.server?.message && <Notice tone="error">{errors.root.server.message}</Notice>}
        {order.payment_status === 'paid' && (
          <Notice tone="warning" title="This order is paid">
            Cancelling doesn&apos;t refund the buyer. Refund them in your payment gateway, then mark the order refunded.
          </Notice>
        )}
        <Field
          label="Reason"
          hint={`Optional. Included in the buyer's cancellation message. ${reasonLength}/${MAX_REASON}`}
          error={errors.reason?.message}
        >
          <Textarea rows={3} placeholder="Out of stock" {...register('reason')} />
        </Field>
        <Checkbox label="Return items to stock" description="Adds the ordered quantities back to your products." {...register('restock')} />
        <Checkbox label="Notify the buyer on WhatsApp" {...register('notify_buyer')} />
      </form>
    </Dialog>
  )
}
