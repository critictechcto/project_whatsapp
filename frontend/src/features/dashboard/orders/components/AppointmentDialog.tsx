import { useMutation } from '@tanstack/react-query'
import { useId, useState } from 'react'
import { Button, Dialog, Field, Input } from '../../../../components/app'
import { fromZonedParts, timeZoneName, toZonedParts } from '../../../../lib/datetime'
import { useWorkspace } from '../../../../lib/workspace'
import { orderMutations, type Order } from '../api'
import { formatDay, formatWindow } from '../format'

type AppointmentDialogProps = {
  order: Order
  onClose: () => void
  onSaved: (order: Order) => void
  onFailed: (error: unknown) => void
}

/** Where the dialog starts: the current appointment, else the start of the window the buyer asked for. */
function appointmentDefaults(order: Order, timeZone: string): { date: string; time: string } {
  if (order.appointment_at) return toZonedParts(order.appointment_at, timeZone)
  const today = toZonedParts(new Date().toISOString(), timeZone).date
  return { date: order.requested_date ?? today, time: order.requested_window?.start ?? '10:00' }
}

/**
 * "Confirm time" for a booking request and "Change time" for a confirmed booking. The date and time are wall
 * clock in the workspace time zone and go to `confirm-booking` as a UTC instant; the buyer is told each time.
 * Mount it only while open, so every opening starts from the order.
 */
export function AppointmentDialog({ order, onClose, onSaved, onFailed }: AppointmentDialogProps) {
  const { timeZone } = useWorkspace()
  const formId = useId()
  const changing = order.status === 'confirmed'
  const [value, setValue] = useState(() => appointmentDefaults(order, timeZone))
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: (appointmentAt: string) => orderMutations.confirmBooking(order.id, { appointment_at: appointmentAt }),
    onSuccess: onSaved,
    onError: onFailed,
  })

  const submit = () => {
    const appointmentAt = fromZonedParts(value.date, value.time, timeZone)
    if (!appointmentAt) {
      setError('Pick a date and a time.')
      return
    }
    setError(null)
    mutation.mutate(appointmentAt)
  }

  const requested = order.requested_window
    ? `The buyer asked for ${formatWindow(order.requested_window)}${order.requested_date ? ` on ${formatDay(order.requested_date)}` : ''}.`
    : ''

  return (
    <Dialog
      size="sm"
      open
      onOpenChange={(open) => {
        if (!open && !mutation.isPending) onClose()
      }}
      dismissible={!mutation.isPending}
      title={changing ? `Change the time of ${order.number}?` : `Confirm ${order.number}?`}
      description={`${requested} The buyer gets a WhatsApp message with the time.`.trim()}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>
            Go back
          </Button>
          <Button type="submit" form={formId} loading={mutation.isPending}>
            {changing ? 'Change time' : 'Confirm time'}
          </Button>
        </>
      }
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault()
          submit()
        }}
      >
        <div className="grid grid-cols-2 gap-3">
          <Field label="Date" required>
            <Input type="date" value={value.date} onChange={(event) => setValue((current) => ({ ...current, date: event.target.value }))} />
          </Field>
          <Field label="Time" required>
            <Input type="time" step={60} value={value.time} onChange={(event) => setValue((current) => ({ ...current, time: event.target.value }))} />
          </Field>
        </div>
        <p className="font-mono text-[12px] text-muted">
          {timeZoneName(timeZone)} · {timeZone}
        </p>
        {error && (
          <p role="alert" className="text-[13px] text-signal">
            {error}
          </p>
        )}
      </form>
    </Dialog>
  )
}
