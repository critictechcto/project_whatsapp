import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { useState, type Dispatch, type SetStateAction } from 'react'
import { api, unwrap } from '../../../api/client'
import { errorMessage } from '../../../api/errors'
import type { Schemas } from '../../../api/types'
import { Button, PageSpinner, TemplatePicker, templateKeys, useToast } from '../../../components/app'
import { useWorkspace } from '../../../lib/workspace'
import { Notice } from '../settings/ui/Notice'
import { SectionCard } from '../settings/ui/SectionCard'
import {
  fetchStoreSettings,
  patchStoreSettings,
  storeQueryKeys,
  useStoreSettings,
  type BookingTemplateField,
  type NotificationKey,
  type StoreSettings,
  type StoreSettingsPatch,
} from './api'
import { StoreFrame } from './components/StoreNav'

type RowKey = NotificationKey | BookingTemplateField
type TemplateMap = Record<RowKey, string | null>
type Row = { key: RowKey; label: string; description: string }

const orderRows: { key: NotificationKey; label: string; description: string }[] = [
  { key: 'confirmed', label: 'Order confirmed', description: 'After checkout, with the total and how the buyer is paying.' },
  { key: 'packed', label: 'Packed', description: 'When you mark the order packed.' },
  { key: 'shipped', label: 'Shipped', description: 'With the courier, AWB number and tracking link.' },
  { key: 'delivered', label: 'Delivered', description: 'When you mark the order delivered.' },
  { key: 'cancelled', label: 'Cancelled', description: 'With the reason for cancelling.' },
  { key: 'payment_reminder', label: 'Payment reminder', description: 'With the payment link, if the buyer hasn’t paid after 15 minutes. Left empty, the default upc_payment_reminder template is used once Meta approves it (it’s created in your account automatically).' },
]

/** Bookings keep their template ids as top-level store settings, not in `notification_templates`. */
const bookingRows: { key: BookingTemplateField; label: string; description: string }[] = [
  { key: 'booking_confirmed_template_id', label: 'Booking confirmed', description: 'When you confirm a booking or change its time, with the appointment time.' },
  { key: 'booking_cancelled_template_id', label: 'Booking cancelled', description: 'When a booking is cancelled.' },
  { key: 'booking_reminder_template_id', label: 'Booking reminder', description: 'Before the appointment, as set under Bookings in Store settings.' },
]

const allRows: Row[] = [...orderRows, ...bookingRows]

function toMap(settings: StoreSettings): TemplateMap {
  const templates = settings.notification_templates ?? {}
  return {
    ...(Object.fromEntries(orderRows.map(({ key }) => [key, templates[key] ?? null])) as Record<NotificationKey, string | null>),
    ...(Object.fromEntries(bookingRows.map(({ key }) => [key, settings[key] ?? null])) as Record<BookingTemplateField, string | null>),
  }
}

export function NotificationsPage() {
  const { workspaceId } = useWorkspace()
  const settings = useStoreSettings(workspaceId)

  return (
    <StoreFrame description="The WhatsApp updates buyers get as their order or booking moves along.">
      <Notice title="When a template is used">
        Inside the buyer's 24-hour window, updates go as a normal WhatsApp message. Outside it, WhatsApp only allows approved templates, so we
        send the template you pick here; without one, that update isn't sent. Under Meta's current pricing, templates may be charged to your
        WhatsApp Business Account.
      </Notice>
      {settings.isPending ? (
        <PageSpinner />
      ) : settings.isError ? (
        <Notice tone="danger" role="alert" title="Couldn't load store settings">
          {errorMessage(settings.error)}
        </Notice>
      ) : (
        <TemplatesEditor settings={settings.data} />
      )}
    </StoreFrame>
  )
}

function TemplatesEditor({ settings }: { settings: StoreSettings }) {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const [templates, setTemplates] = useState<TemplateMap>(() => toMap(settings))
  const [starterResult, setStarterResult] = useState<Schemas['StarterTemplatesResult'] | null>(null)
  const saved = toMap(settings)

  const starter = useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/store/starter-templates/')),
    onSuccess: async (result) => {
      setStarterResult(result)
      void queryClient.invalidateQueries({ queryKey: storeQueryKeys.checklist(workspaceId) })
      void queryClient.invalidateQueries({ queryKey: templateKeys.all(workspaceId) })
      // The API maps new templates onto empty rows; keep the seller's unsaved picks for the others.
      const fresh = await queryClient.fetchQuery({
        queryKey: storeQueryKeys.settings(workspaceId),
        queryFn: ({ signal }) => fetchStoreSettings(signal),
        staleTime: 0,
      })
      const mapped = toMap(fresh)
      setTemplates((current) => Object.fromEntries(allRows.map(({ key }) => [key, current[key] ?? mapped[key]])) as TemplateMap)
    },
  })

  return (
    <div className="flex flex-col gap-6">
      <SectionCard
        id="starter-templates"
        title="Starter templates"
        description="Creates ready-made order and booking templates (Utility, English) in your WhatsApp Business Account and fills in empty rows below. Meta reviews new templates before they can be sent."
        actions={
          <Button variant="secondary" loading={starter.isPending} onClick={() => starter.mutate()}>
            Create starter templates
          </Button>
        }
      >
        {starter.isError ? (
          <Notice tone="danger" role="alert">
            {errorMessage(starter.error)}
          </Notice>
        ) : starterResult ? (
          <div role="status" className="grid gap-4 text-sm sm:grid-cols-2">
            <div>
              <p className="font-medium text-ink">Created</p>
              {starterResult.created.length ? (
                <ul aria-label="Created templates" className="mt-1 flex flex-col gap-0.5 font-mono text-[12.5px] text-ink">
                  {starterResult.created.map((name) => (
                    <li key={name}>{name}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-muted">Nothing new; you already have them all.</p>
              )}
            </div>
            <div>
              <p className="font-medium text-ink">Already in your account</p>
              {starterResult.existing.length ? (
                <ul aria-label="Existing templates" className="mt-1 flex flex-col gap-0.5 font-mono text-[12.5px] text-muted">
                  {starterResult.existing.map((name) => (
                    <li key={name}>{name}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-muted">None.</p>
              )}
            </div>
          </div>
        ) : (
          <p className="text-[13px] text-muted">
            Templates in review show up in the pickers below once Meta approves them. You can also pick any approved Utility template of your
            own.
          </p>
        )}
      </SectionCard>

      <TemplateRowsCard
        id="order-templates"
        title="Order update templates"
        description="Approved Utility templates used outside the 24-hour window."
        saveLabel="Save templates"
        successMessage="Notification templates saved"
        rows={orderRows}
        templates={templates}
        saved={saved}
        setTemplates={setTemplates}
        toPatch={(map) => ({
          notification_templates: Object.fromEntries(orderRows.map(({ key }) => [key, map[key]])) as Record<NotificationKey, string | null>,
        })}
      />

      <TemplateRowsCard
        id="booking-templates"
        title="Booking update templates"
        description="For services. Approved Utility templates used outside the 24-hour window."
        saveLabel="Save booking templates"
        successMessage="Booking templates saved"
        rows={bookingRows}
        templates={templates}
        saved={saved}
        setTemplates={setTemplates}
        toPatch={(map) => Object.fromEntries(bookingRows.map(({ key }) => [key, map[key]])) as StoreSettingsPatch}
      />
    </div>
  )
}

type TemplateRowsCardProps = {
  id: string
  title: string
  description: string
  saveLabel: string
  successMessage: string
  rows: readonly Row[]
  templates: TemplateMap
  saved: TemplateMap
  setTemplates: Dispatch<SetStateAction<TemplateMap>>
  toPatch: (map: TemplateMap) => StoreSettingsPatch
}

/** One card of template pickers with its own save, so saving orders never sends unsaved booking picks. */
function TemplateRowsCard({ id, title, description, saveLabel, successMessage, rows, templates, saved, setTemplates, toPatch }: TemplateRowsCardProps) {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const dirty = rows.some(({ key }) => templates[key] !== saved[key])

  const save = useMutation({
    mutationFn: () => patchStoreSettings(toPatch(templates)),
    onSuccess: (next) => {
      queryClient.setQueryData(storeQueryKeys.settings(workspaceId), next)
      void queryClient.invalidateQueries({ queryKey: storeQueryKeys.checklist(workspaceId) })
      const mapped = toMap(next)
      setTemplates((current) => ({ ...current, ...Object.fromEntries(rows.map(({ key }) => [key, mapped[key]])) }))
      toast({ title: successMessage, tone: 'success' })
    },
  })

  const discard = () => setTemplates((current) => ({ ...current, ...Object.fromEntries(rows.map(({ key }) => [key, saved[key]])) }))

  return (
    <SectionCard
      id={id}
      title={title}
      description={description}
      footer={
        <>
          {save.isError && (
            <p role="alert" className="mr-auto text-[13px] text-signal">
              {errorMessage(save.error)}
            </p>
          )}
          <Button variant="secondary" disabled={!dirty || save.isPending} onClick={discard}>
            Discard
          </Button>
          <Button disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>
            {saveLabel}
          </Button>
        </>
      }
    >
      <ul className="-mx-5 -my-4 divide-y divide-line-2">
        {rows.map(({ key, label, description: rowDescription }) => (
          <li key={key} className="grid gap-3 px-5 py-4 md:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]">
            <div>
              <p className="font-medium text-ink">{label}</p>
              <p className="text-[13px] text-muted">{rowDescription}</p>
            </div>
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <TemplatePicker
                  aria-label={`Template for ${label}`}
                  category="UTILITY"
                  showPreview={false}
                  value={templates[key]}
                  onChange={(template) => setTemplates((current) => ({ ...current, [key]: template?.id ?? null }))}
                />
              </div>
              {templates[key] && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-1"
                  aria-label={`Clear template for ${label}`}
                  icon={<X className="size-4" aria-hidden="true" />}
                  onClick={() => setTemplates((current) => ({ ...current, [key]: null }))}
                />
              )}
            </div>
          </li>
        ))}
      </ul>
    </SectionCard>
  )
}
