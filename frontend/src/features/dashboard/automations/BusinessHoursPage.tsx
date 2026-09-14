import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, Plus, Trash2 } from 'lucide-react'
import { useForm, useWatch, type FieldErrors } from 'react-hook-form'
import { Link } from 'react-router'
import { api, unwrap } from '../../../api/client'
import { applyApiErrorToForm, errorMessage } from '../../../api/errors'
import { Button, Input, PageHeader, Skeleton, Switch, useToast } from '../../../components/app'
import { timeZoneName } from '../../../lib/datetime'
import { useWorkspace } from '../../../lib/workspace'
import { Notice } from '../campaigns/components/Notice'
import { automationKeys, type BusinessHours } from './api'
import {
  businessHoursSchema,
  dayNames,
  defaultSlot,
  formToSchedule,
  hoursToForm,
  isOvernight,
  type BusinessHoursFormValues,
  type DayFormValues,
} from './businessHours'
import { AutomationsNav } from './components/AutomationsNav'

export function BusinessHoursPage() {
  const { workspaceId, can } = useWorkspace()
  const hours = useQuery({
    queryKey: automationKeys.custom(workspaceId, 'business-hours'),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/automations/business-hours/', { signal })),
  })

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Business hours" description="When your team is available. The “Outside business hours” trigger uses this." />
      <AutomationsNav />
      {hours.isError ? (
        <Notice tone="error" title="Couldn't load business hours">
          {errorMessage(hours.error)}
        </Notice>
      ) : !hours.data ? (
        <Skeleton className="h-96 w-full max-w-3xl" />
      ) : (
        <BusinessHoursForm hours={hours.data} readOnly={!can('admin')} />
      )}
    </div>
  )
}

type DayErrors = NonNullable<FieldErrors<BusinessHoursFormValues>['days']>[number]

function BusinessHoursForm({ hours, readOnly }: { hours: BusinessHours; readOnly: boolean }) {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const form = useForm<BusinessHoursFormValues>({ resolver: zodResolver(businessHoursSchema), defaultValues: hoursToForm(hours) })
  const {
    control,
    setValue,
    getValues,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting, isSubmitted },
  } = form
  const days = useWatch({ control, name: 'days' })
  const enabled = useWatch({ control, name: 'enabled' })
  const options = { shouldDirty: true, shouldValidate: isSubmitted }

  const onSubmit = handleSubmit(async (values) => {
    try {
      const saved = await unwrap(
        api.PATCH('/api/v1/automations/business-hours/', { body: { enabled: values.enabled, schedule: formToSchedule(values) } }),
      )
      queryClient.setQueryData(automationKeys.custom(workspaceId, 'business-hours'), saved)
      reset(hoursToForm(saved))
      toast({ title: 'Business hours saved' })
    } catch (error) {
      applyApiErrorToForm(error, setError, { fields: [] })
    }
  })

  const setDay = (index: number, day: DayFormValues) => setValue(`days.${index}`, day, options)

  const copyMonday = () => {
    const monday = getValues('days.0')
    for (let index = 1; index <= 4; index += 1) {
      setDay(index, { open: monday.open, slots: monday.slots.map((slot) => ({ ...slot })) })
    }
  }

  return (
    <form noValidate onSubmit={(event) => void onSubmit(event)} className="flex max-w-3xl flex-col gap-6">
      {readOnly && <Notice>You can view business hours. Only admins and owners can change them.</Notice>}
      {errors.root?.server?.message && <Notice tone="error">{errors.root.server.message}</Notice>}
      {errors.enabled?.message && <Notice tone="error">{errors.enabled.message}</Notice>}

      <fieldset disabled={readOnly} className="flex min-w-0 flex-col gap-6">
        <div className="flex flex-col gap-4 rounded-xl border border-line bg-card p-5">
          <Switch
            checked={enabled}
            onCheckedChange={(checked) => setValue('enabled', checked, options)}
            label="Use business hours"
            description="When this is off, the “Outside business hours” trigger never runs."
            disabled={readOnly}
          />
          <dl className="text-sm">
            <dt className="text-[12px] text-muted">Time zone</dt>
            <dd className="text-ink">
              {timeZoneName(hours.time_zone)} <span className="font-mono text-[12px] text-muted">({hours.time_zone})</span>
            </dd>
            <dd className="mt-0.5 text-[12.5px] text-muted">
              Hours follow the workspace time zone, which you can change in{' '}
              <Link to={`/app/w/${workspaceId}/settings`} className="text-accent-2 underline underline-offset-4">
                settings
              </Link>
              .
            </dd>
          </dl>
        </div>

        <section aria-labelledby="weekly-hours-heading" className="rounded-xl border border-line bg-card">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line-2 px-5 py-3.5">
            <h2 id="weekly-hours-heading" className="font-display text-base font-semibold text-ink">
              Weekly hours
            </h2>
            {!readOnly && (
              <Button variant="secondary" size="sm" icon={<Copy className="size-4" aria-hidden="true" />} onClick={copyMonday}>
                Copy Monday to weekdays
              </Button>
            )}
          </div>
          <ul className="divide-y divide-line-2">
            {days.map((day, index) => (
              <DayRow
                key={dayNames[index]}
                index={index}
                day={day}
                errors={errors.days?.[index]}
                disabled={readOnly}
                onChange={(next) => setDay(index, next)}
              />
            ))}
          </ul>
          <p className="border-t border-line-2 px-5 py-3 text-[12.5px] text-muted">
            Overnight hours are allowed: set a closing time earlier than the opening time, for example 22:00 to 02:00, and the slot runs
            past midnight into the next day.
          </p>
        </section>
      </fieldset>

      {!readOnly && (
        <div className="flex justify-end">
          <Button type="submit" loading={isSubmitting}>
            Save business hours
          </Button>
        </div>
      )}
    </form>
  )
}

type DayRowProps = {
  index: number
  day: DayFormValues
  errors: DayErrors | undefined
  disabled: boolean
  onChange: (day: DayFormValues) => void
}

function DayRow({ index, day, errors, disabled, onChange }: DayRowProps) {
  const name = dayNames[index]
  const updateSlot = (position: number, patch: Partial<DayFormValues['slots'][number]>) =>
    onChange({ ...day, slots: day.slots.map((slot, i) => (i === position ? { ...slot, ...patch } : slot)) })

  return (
    <li className="grid gap-3 px-5 py-4 sm:grid-cols-[150px_minmax(0,1fr)]">
      <div className="flex items-center justify-between gap-2 sm:flex-col sm:items-start">
        <span className="text-sm font-medium text-ink">{name}</span>
        <Switch
          checked={day.open}
          onCheckedChange={(open) => onChange({ open, slots: open && !day.slots.length ? [{ ...defaultSlot }] : day.slots })}
          label={`Open on ${name}`}
          hideLabel
          disabled={disabled}
        />
      </div>

      {!day.open ? (
        <p className="self-center text-sm text-muted">Closed</p>
      ) : (
        <div className="flex flex-col gap-2">
          <ul className="flex flex-col gap-2">
            {day.slots.map((slot, position) => {
              const slotErrors = errors?.slots?.[position]
              const message = slotErrors?.start?.message ?? slotErrors?.end?.message
              return (
                <li key={position} className="flex flex-wrap items-center gap-2">
                  <Input
                    type="time"
                    aria-label={`${name} slot ${position + 1} opens`}
                    value={slot.start}
                    onChange={(event) => updateSlot(position, { start: event.target.value })}
                    aria-invalid={slotErrors?.start ? true : undefined}
                    className="w-32"
                  />
                  <span className="text-sm text-muted" aria-hidden="true">
                    to
                  </span>
                  <Input
                    type="time"
                    aria-label={`${name} slot ${position + 1} closes`}
                    value={slot.end}
                    onChange={(event) => updateSlot(position, { end: event.target.value })}
                    aria-invalid={slotErrors?.end ? true : undefined}
                    className="w-32"
                  />
                  {!disabled && (
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Remove ${name} slot ${position + 1}`}
                      icon={<Trash2 className="size-4" aria-hidden="true" />}
                      onClick={() => onChange({ ...day, slots: day.slots.filter((_, i) => i !== position) })}
                    />
                  )}
                  {isOvernight(slot) && <span className="text-[12.5px] text-muted">Overnight: closes {slot.end} the next day</span>}
                  {message && <p className="w-full text-[13px] text-signal">{message}</p>}
                </li>
              )
            })}
          </ul>
          {errors?.slots?.message && <p className="text-[13px] text-signal">{errors.slots.message}</p>}
          {!disabled && (
            <div>
              <Button
                variant="link"
                size="sm"
                icon={<Plus className="size-4" aria-hidden="true" />}
                onClick={() => onChange({ ...day, slots: [...day.slots, { ...defaultSlot }] })}
              >
                Add hours
              </Button>
            </div>
          )}
        </div>
      )}
    </li>
  )
}
