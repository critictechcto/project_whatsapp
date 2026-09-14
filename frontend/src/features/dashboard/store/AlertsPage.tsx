import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { BellRing, Plus } from 'lucide-react'
import { useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'
import { api, unwrap } from '../../../api/client'
import { applyApiErrorToForm, errorMessage, isApiError } from '../../../api/errors'
import { Button, Checkbox, Dialog, EmptyState, Field, Input, StatusBadge, Table, useToast, type Column, type Tone } from '../../../components/app'
import { formatDateTime, formatRelative } from '../../../lib/datetime'
import { useRealtimeEvent } from '../../../lib/realtime/hooks'
import { useWorkspace } from '../../../lib/workspace'
import { ConfirmDialog } from '../settings/ui/ConfirmDialog'
import { Notice } from '../settings/ui/Notice'
import { SectionCard } from '../settings/ui/SectionCard'
import {
  storeQueryKeys,
  useAlertRecipients,
  usePlatformAlerts,
  type AlertEvent,
  type AlertRecipient,
  type AlertRecipientStatus,
} from './api'
import { StoreFrame } from './components/StoreNav'

export const MAX_ALERT_RECIPIENTS = 3
const ALERT_EVENTS: readonly AlertEvent[] = ['new_order', 'needs_attention', 'order_cancelled']

const eventLabels: Record<AlertEvent, { label: string; description: string }> = {
  new_order: { label: 'New orders', description: 'With buttons to mark it packed, shipped or cancel it.' },
  needs_attention: { label: 'Orders that need attention', description: 'For example a payment that arrived for an expired order.' },
  order_cancelled: { label: 'Cancelled orders', description: 'When a buyer cancels or an order expires unpaid.' },
}

const recipientStatus: Record<AlertRecipientStatus, { label: string; tone: Tone }> = {
  pending: { label: 'Waiting for Confirm', tone: 'amber' },
  verified: { label: 'Confirmed', tone: 'green' },
  opted_out: { label: 'Stopped', tone: 'neutral' },
}

/** `+919829012345` → `+91 98290 12345`. */
function formatPhone(e164: string) {
  const match = /^\+91(\d{5})(\d{5})$/.exec(e164)
  return match ? `+91 ${match[1]} ${match[2]}` : e164
}

export function AlertsPage() {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const platform = usePlatformAlerts(workspaceId)
  const recipients = useAlertRecipients(workspaceId)
  const [dialog, setDialog] = useState<{ mode: 'add' } | { mode: 'edit'; recipient: AlertRecipient } | null>(null)
  const [removing, setRemoving] = useState<AlertRecipient | null>(null)

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: storeQueryKeys.recipients(workspaceId) }),
      queryClient.invalidateQueries({ queryKey: storeQueryKeys.checklist(workspaceId) }),
    ])

  useRealtimeEvent('alert_recipient.updated', () => void refresh())

  const resend = useMutation({
    mutationFn: (recipient: AlertRecipient) =>
      unwrap(api.POST('/api/v1/seller-alerts/recipients/{id}/resend-verification/', { params: { path: { id: recipient.id } } })),
    onSuccess: (_saved, recipient) => {
      void refresh()
      toast({ title: 'Confirmation sent', description: `Ask ${recipient.name} to tap Confirm in the WhatsApp message from UpChatz.`, tone: 'success' })
    },
    onError: (error) => toast({ title: "Couldn't send the confirmation", description: errorMessage(error), tone: 'error' }),
  })

  const remove = useMutation({
    mutationFn: (recipient: AlertRecipient) => unwrap(api.DELETE('/api/v1/seller-alerts/recipients/{id}/', { params: { path: { id: recipient.id } } })),
    onSuccess: (_data, recipient) => {
      setRemoving(null)
      void refresh()
      toast({ title: `${recipient.name} won't get alerts any more` })
    },
    onError: (error) => {
      setRemoving(null)
      toast({ title: "Couldn't remove the number", description: errorMessage(error), tone: 'error' })
    },
  })

  const available = platform.data?.available ?? false
  const displayNumber = platform.data?.display_phone_number ?? ''
  const list = recipients.data ?? []
  const atLimit = list.length >= MAX_ALERT_RECIPIENTS

  const columns: Column<AlertRecipient>[] = [
    {
      id: 'name',
      header: 'Name',
      cell: (recipient) => (
        <div className="min-w-0">
          <p className="font-medium text-ink">{recipient.name}</p>
          <p className="font-mono text-[12px] text-muted">{formatPhone(recipient.phone_e164)}</p>
        </div>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      cell: (recipient) => <StatusBadge tone={recipientStatus[recipient.status].tone}>{recipientStatus[recipient.status].label}</StatusBadge>,
    },
    {
      id: 'events',
      header: 'Alerts',
      hideOnMobile: true,
      cell: (recipient) => (
        <span className="text-[13px]">{(recipient.events ?? ALERT_EVENTS).map((event) => eventLabels[event].label).join(', ') || '—'}</span>
      ),
    },
    {
      id: 'verified',
      header: 'Confirmed',
      hideOnMobile: true,
      cell: (recipient) =>
        recipient.verified_at ? (
          <time dateTime={recipient.verified_at} title={formatDateTime(recipient.verified_at)} className="text-[13px] text-muted">
            {formatRelative(recipient.verified_at)}
          </time>
        ) : (
          <span className="text-[13px] text-muted">—</span>
        ),
    },
    {
      id: 'actions',
      header: <span className="sr-only">Actions</span>,
      align: 'right',
      cell: (recipient) => (
        <div className="flex flex-wrap justify-end gap-1">
          {recipient.status !== 'verified' && (
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Resend confirmation to ${recipient.name}`}
              loading={resend.isPending && resend.variables?.id === recipient.id}
              disabled={!available}
              onClick={() => resend.mutate(recipient)}
            >
              Resend
            </Button>
          )}
          <Button variant="ghost" size="sm" aria-label={`Edit alerts for ${recipient.name}`} onClick={() => setDialog({ mode: 'edit', recipient })}>
            Edit
          </Button>
          <Button variant="ghost" size="sm" className="text-signal" aria-label={`Remove ${recipient.name}`} onClick={() => setRemoving(recipient)}>
            Remove
          </Button>
        </div>
      ),
    },
  ]

  const addButton = (
    <Button icon={<Plus className="size-4" aria-hidden="true" />} disabled={!available || atLimit} onClick={() => setDialog({ mode: 'add' })}>
      Add number
    </Button>
  )

  return (
    <StoreFrame description="Get every new order on your personal WhatsApp and act on it from there.">
      {platform.data && !available && (
        <Notice tone="warning" title="Order alerts aren't available yet">
          Alerts come from the UpChatz alerts number, which isn't set up yet. You'll still see every order on the Orders page.
        </Notice>
      )}
      {(platform.isError || recipients.isError) && (
        <Notice tone="danger" role="alert" title="Couldn't load order alerts">
          {errorMessage(platform.error ?? recipients.error)}
        </Notice>
      )}

      <SectionCard
        id="alert-recipients"
        title="Alert numbers"
        description={
          available
            ? `Alerts are sent from UpChatz (${displayNumber}) to up to ${MAX_ALERT_RECIPIENTS} numbers. Save that number in your phone.`
            : `Up to ${MAX_ALERT_RECIPIENTS} personal WhatsApp numbers can get alerts.`
        }
        actions={list.length > 0 ? addButton : undefined}
      >
        <div className="flex flex-col gap-3">
          <Table
            caption="Numbers that get order alerts"
            columns={columns}
            rows={list}
            getRowId={(recipient) => recipient.id}
            loading={recipients.isPending}
            empty={
              <EmptyState
                icon={<BellRing />}
                title="No alert numbers yet"
                description="Add your own WhatsApp number to hear about new orders straight away."
                action={addButton}
              />
            }
          />
          {atLimit && <p className="text-[13px] text-muted">You've added the maximum of {MAX_ALERT_RECIPIENTS} numbers. Remove one to add another.</p>}
        </div>
      </SectionCard>

      <SectionCard id="alert-commands" title="Reply from WhatsApp" description="Only confirmed numbers can use these.">
        <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-[max-content_1fr]">
          <dt className="font-medium text-ink">Mark packed / Mark shipped / Cancel</dt>
          <dd className="text-muted">Buttons on each new-order alert. After Mark shipped, reply with the courier name and AWB number.</dd>
          <dt className="font-mono text-ink">ORDERS</dt>
          <dd className="text-muted">Lists your open orders.</dd>
          <dt className="font-mono text-ink">HELP</dt>
          <dd className="text-muted">Shows what you can do from WhatsApp.</dd>
          <dt className="font-mono text-ink">STOP</dt>
          <dd className="text-muted">Stops alerts to that number. Resend the confirmation here to start again.</dd>
        </dl>
      </SectionCard>

      {dialog && (
        <RecipientDialog
          key={dialog.mode === 'edit' ? dialog.recipient.id : 'add'}
          recipient={dialog.mode === 'edit' ? dialog.recipient : null}
          displayNumber={displayNumber}
          onClose={() => setDialog(null)}
          onSaved={() => void refresh()}
        />
      )}
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={removing ? `Remove ${removing.name}?` : 'Remove number?'}
        description="This number stops getting order alerts and can't act on orders from WhatsApp."
        confirmLabel="Remove"
        loading={remove.isPending}
        onConfirm={() => removing && remove.mutate(removing)}
      />
    </StoreFrame>
  )
}

const eventsSchema = z.array(z.enum(['new_order', 'needs_attention', 'order_cancelled'])).min(1, 'Choose at least one alert.')

function recipientSchema(editing: boolean) {
  return z.object({
    name: z.string().trim().min(1, 'Enter a name.').max(60, 'Use 60 characters or fewer.'),
    phone: editing ? z.string() : z.string().trim().regex(/^[6-9]\d{9}$/, 'Enter a 10-digit Indian mobile number.'),
    events: eventsSchema,
  })
}

type RecipientFormValues = z.infer<ReturnType<typeof recipientSchema>>

function RecipientDialog({
  recipient,
  displayNumber,
  onClose,
  onSaved,
}: {
  recipient: AlertRecipient | null
  displayNumber: string
  onClose: () => void
  onSaved: () => void
}) {
  const { toast } = useToast()
  const editing = recipient !== null
  const {
    control,
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<RecipientFormValues>({
    resolver: zodResolver(recipientSchema(editing)),
    defaultValues: { name: recipient?.name ?? '', phone: '', events: [...(recipient?.events ?? ALERT_EVENTS)] },
  })

  const onSubmit = handleSubmit(async (values) => {
    try {
      if (recipient) {
        await unwrap(
          api.PATCH('/api/v1/seller-alerts/recipients/{id}/', {
            params: { path: { id: recipient.id } },
            body: { name: values.name.trim(), events: values.events },
          }),
        )
        toast({ title: 'Alerts updated', tone: 'success' })
      } else {
        const created = await unwrap(
          api.POST('/api/v1/seller-alerts/recipients/', { body: { name: values.name.trim(), phone_e164: `+91${values.phone.trim()}`, events: values.events } }),
        )
        toast({ title: 'Confirmation sent', description: `${created.name} needs to tap Confirm in the WhatsApp message from UpChatz.`, tone: 'success' })
      }
      onSaved()
      onClose()
    } catch (error) {
      // Another admin may have filled the last slot; refresh the table so it shows the limit too.
      if (isApiError(error, 'alert_recipient_limit')) onSaved()
      applyApiErrorToForm(error, setError, { fieldMap: { phone_e164: 'phone' }, fields: ['name', 'phone', 'events'] })
    }
  })

  return (
    <Dialog
      open
      onOpenChange={(open) => !open && onClose()}
      dismissible={!isSubmitting}
      title={editing ? `Edit alerts for ${recipient.name}` : 'Add alert number'}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button type="submit" form="alert-recipient-form" loading={isSubmitting}>
            {editing ? 'Save' : 'Add and send confirmation'}
          </Button>
        </>
      }
    >
      <form id="alert-recipient-form" noValidate onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-4">
        <Field label="Name" error={errors.name?.message} required>
          <Input {...register('name')} maxLength={60} autoComplete="off" placeholder="Rohit (owner)" />
        </Field>
        {editing ? (
          <p className="text-sm text-muted">
            WhatsApp number: <span className="font-mono text-ink">{formatPhone(recipient.phone_e164)}</span>
          </p>
        ) : (
          <Field label="WhatsApp number" hint="A 10-digit Indian mobile number. We add +91." error={errors.phone?.message} required>
            <Input {...register('phone')} prefix="+91" inputMode="numeric" autoComplete="tel-national" maxLength={10} placeholder="98290 12345" className="pl-12" />
          </Field>
        )}
        <Controller
          control={control}
          name="events"
          render={({ field }) => (
            <fieldset className="flex flex-col gap-2.5" aria-describedby={errors.events ? 'alert-events-error' : undefined}>
              <legend className="mb-1 text-[13px] font-medium text-ink">Send alerts for</legend>
              {ALERT_EVENTS.map((event) => (
                <Checkbox
                  key={event}
                  label={eventLabels[event].label}
                  description={eventLabels[event].description}
                  checked={field.value.includes(event)}
                  onChange={(change) =>
                    field.onChange(change.target.checked ? ALERT_EVENTS.filter((item) => item === event || field.value.includes(item)) : field.value.filter((item) => item !== event))
                  }
                />
              ))}
              {errors.events?.message && (
                <p id="alert-events-error" className="text-[13px] text-signal">
                  {errors.events.message}
                </p>
              )}
            </fieldset>
          )}
        />
        {!editing && (
          <Notice title="They need to tap Confirm">
            You'll get a WhatsApp message from UpChatz{displayNumber ? ` (${displayNumber})` : ''} — tap Confirm to start getting alerts.
          </Notice>
        )}
        {errors.root?.server?.message && (
          <Notice tone="danger" role="alert">
            {errors.root.server.message}
          </Notice>
        )}
      </form>
    </Dialog>
  )
}
