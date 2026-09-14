import { zodResolver } from '@hookform/resolvers/zod'
import { useId } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { applyApiErrorToForm, isApiError } from '../../../../api/errors'
import { Button, Checkbox, Dialog, Field, Input } from '../../../../components/app'
import { orderMutations, type Order } from '../api'
import { isHttpsUrl } from '../format'
import { Notice } from './Notice'

const schema = z.object({
  courier_name: z.string().trim().min(1, 'Enter the courier name.').max(100, 'Use at most 100 characters.'),
  awb_number: z.string().trim().min(1, 'Enter the AWB number.').max(100, 'Use at most 100 characters.'),
  tracking_url: z
    .string()
    .trim()
    .refine((value) => !value || isHttpsUrl(value), 'Enter a full link that starts with https://'),
  notify_buyer: z.boolean(),
})

type FormValues = z.infer<typeof schema>

const fields = ['courier_name', 'awb_number', 'tracking_url', 'notify_buyer'] as const

type ShipDialogProps = {
  order: Order
  onClose: () => void
  onShipped: (order: Order) => void
  /** Anything other than field errors, such as 409 `invalid_order_transition`. */
  onFailed: (error: unknown) => void
}

/** Mount it only while open, so every opening starts with a fresh form. */
export function ShipDialog({ order, onClose, onShipped, onFailed }: ShipDialogProps) {
  const formId = useId()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { courier_name: '', awb_number: '', tracking_url: '', notify_buyer: true },
  })

  const onSubmit = handleSubmit(async (values) => {
    try {
      const updated = await orderMutations.transition(order.id, {
        to_status: 'shipped',
        courier_name: values.courier_name,
        awb_number: values.awb_number,
        ...(values.tracking_url ? { tracking_url: values.tracking_url } : {}),
        notify_buyer: values.notify_buyer,
      })
      onShipped(updated)
    } catch (error) {
      if (isApiError(error, 'invalid')) {
        applyApiErrorToForm(error, setError, { fields })
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
      title={`Mark ${order.number} shipped`}
      description="Add the courier details the buyer needs to track the parcel."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
            Go back
          </Button>
          <Button type="submit" form={formId} loading={isSubmitting}>
            Mark shipped
          </Button>
        </>
      }
    >
      <form id={formId} onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        {errors.root?.server?.message && <Notice tone="error">{errors.root.server.message}</Notice>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Courier" required error={errors.courier_name?.message}>
            <Input autoComplete="off" placeholder="Delhivery" {...register('courier_name')} />
          </Field>
          <Field label="AWB number" required error={errors.awb_number?.message}>
            <Input autoComplete="off" className="font-mono" placeholder="DL48213990" {...register('awb_number')} />
          </Field>
        </div>
        <Field label="Tracking link" hint="Optional. The courier's tracking page for this parcel." error={errors.tracking_url?.message}>
          <Input type="url" inputMode="url" placeholder="https://" {...register('tracking_url')} />
        </Field>
        <Checkbox
          label="Notify the buyer on WhatsApp"
          description="Sends the courier, AWB number and tracking link."
          {...register('notify_buyer')}
        />
      </form>
    </Dialog>
  )
}
