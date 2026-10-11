import { zodResolver } from '@hookform/resolvers/zod'
import { useId } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'
import { applyApiErrorToForm, isApiError } from '../../../../api/errors'
import { Button, Checkbox, Dialog, Field, Input, Switch } from '../../../../components/app'
import { orderMutations, type Order } from '../api'
import { isHttpsUrl } from '../format'
import { Notice } from './Notice'

// Tracking details are on by default; a seller without a courier or AWB turns them off per shipment.
const schema = z
  .object({
    add_tracking: z.boolean(),
    courier_name: z.string().trim().max(100, 'Use at most 100 characters.'),
    awb_number: z.string().trim().max(100, 'Use at most 100 characters.'),
    tracking_url: z.string().trim(),
    notify_buyer: z.boolean(),
  })
  .superRefine((values, ctx) => {
    if (!values.add_tracking) return
    if (!values.courier_name) ctx.addIssue({ code: 'custom', path: ['courier_name'], message: 'Enter the courier name.' })
    if (!values.awb_number) ctx.addIssue({ code: 'custom', path: ['awb_number'], message: 'Enter the AWB number.' })
    if (values.tracking_url && !isHttpsUrl(values.tracking_url)) {
      ctx.addIssue({ code: 'custom', path: ['tracking_url'], message: 'Enter a full link that starts with https://' })
    }
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
    control,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { add_tracking: true, courier_name: '', awb_number: '', tracking_url: '', notify_buyer: true },
  })
  const addTracking = useWatch({ control, name: 'add_tracking' })

  const onSubmit = handleSubmit(async (values) => {
    try {
      const tracking = values.add_tracking
        ? {
            courier_name: values.courier_name,
            awb_number: values.awb_number,
            ...(values.tracking_url ? { tracking_url: values.tracking_url } : {}),
          }
        : {}
      const updated = await orderMutations.transition(order.id, {
        to_status: 'shipped',
        ...tracking,
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
      description={
        addTracking
          ? 'Add the courier details the buyer needs to track the parcel.'
          : 'The order is marked shipped without a courier or AWB number.'
      }
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
        <Controller
          control={control}
          name="add_tracking"
          render={({ field }) => (
            <Switch
              checked={field.value}
              onCheckedChange={field.onChange}
              label="Add tracking details"
              description="Turn off if you deliver yourself or don't have a courier and AWB number."
            />
          )}
        />
        {addTracking && (
          <>
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
          </>
        )}
        <Checkbox
          label="Notify the buyer on WhatsApp"
          description={addTracking ? 'Sends the courier, AWB number and tracking link.' : 'Tells the buyer the order is on its way.'}
          {...register('notify_buyer')}
        />
      </form>
    </Dialog>
  )
}
