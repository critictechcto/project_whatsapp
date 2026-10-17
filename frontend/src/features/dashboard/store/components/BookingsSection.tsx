import { Plus, Trash2 } from 'lucide-react'
import { Controller, useFieldArray, useWatch, type Control, type FieldErrors, type UseFormRegister } from 'react-hook-form'
import { Button, Checkbox, Field, Input, Switch } from '../../../../components/app'
import { SectionCard } from '../../settings/ui/SectionCard'
import { MAX_BOOKING_WINDOWS, WINDOW_LABEL_MAX, weekdays, type SettingsFormValues } from '../settingsForm'

type BookingsSectionProps = {
  control: Control<SettingsFormValues>
  register: UseFormRegister<SettingsFormValues>
  errors: FieldErrors<SettingsFormValues>
}

/** Days, time windows, pay at the shop and reminders for services (bookings). */
export function BookingsSection({ control, register, errors }: BookingsSectionProps) {
  const windows = useFieldArray({ control, name: 'booking_windows' })
  const labels = useWatch({ control, name: 'booking_windows' })
  const windowsError = errors.booking_windows?.root?.message ?? errors.booking_windows?.message

  return (
    <SectionCard
      id="store-bookings"
      title="Bookings"
      description="For services. Buyers pick a day and a time window, and you confirm the exact time on the order."
    >
      <div className="flex flex-col gap-6">
        <Controller
          control={control}
          name="pay_at_shop_enabled"
          render={({ field }) => (
            <Switch
              checked={field.value}
              onCheckedChange={field.onChange}
              label="Offer pay at the shop"
              description="Buyers can book now and pay after the service. You mark it paid on the booking."
            />
          )}
        />

        <Controller
          control={control}
          name="booking_days"
          render={({ field }) => (
            <fieldset aria-describedby={errors.booking_days ? 'booking-days-error' : undefined}>
              <legend className="text-sm font-medium text-ink">Open for bookings</legend>
              <div className="mt-2 flex flex-wrap gap-x-5 gap-y-3">
                {weekdays.map((day) => (
                  <Checkbox
                    key={day.value}
                    label={day.label}
                    checked={field.value.includes(day.value)}
                    onChange={(event) =>
                      field.onChange(
                        event.target.checked
                          ? [...field.value, day.value].sort((a, b) => a - b)
                          : field.value.filter((value) => value !== day.value),
                      )
                    }
                  />
                ))}
              </div>
              {errors.booking_days && (
                <p id="booking-days-error" role="alert" className="mt-1.5 text-[13px] text-signal">
                  {errors.booking_days.message}
                </p>
              )}
            </fieldset>
          )}
        />

        <fieldset className="flex flex-col gap-3">
          <legend className="text-sm font-medium text-ink">Time windows</legend>
          <p className="-mt-1 text-[13px] text-muted">
            Buyers choose one of these. Up to {MAX_BOOKING_WINDOWS}; times are in your workspace time zone.
          </p>
          <ul aria-label="Time windows" className="flex flex-col gap-3">
            {windows.fields.map((item, index) => {
              const rowErrors = errors.booking_windows?.[index]
              const name = labels?.[index]?.label?.trim() || `window ${index + 1}`
              return (
                <li key={item.id} className="grid grid-cols-2 items-start gap-3 sm:grid-cols-[minmax(0,1fr)_8rem_8rem_auto]">
                  <Field label={`Window ${index + 1} name`} error={rowErrors?.label?.message} className="col-span-2 sm:col-span-1">
                    <Input {...register(`booking_windows.${index}.label`)} maxLength={WINDOW_LABEL_MAX} autoComplete="off" placeholder="Morning" />
                  </Field>
                  <Field label="Starts" error={rowErrors?.start?.message}>
                    <Input type="time" step={60} {...register(`booking_windows.${index}.start`)} />
                  </Field>
                  <Field label="Ends" error={rowErrors?.end?.message}>
                    <Input type="time" step={60} {...register(`booking_windows.${index}.end`)} />
                  </Field>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="col-span-2 justify-self-start sm:col-span-1 sm:mt-6"
                    icon={<Trash2 className="size-4" aria-hidden="true" />}
                    aria-label={`Remove ${name}`}
                    disabled={windows.fields.length <= 1}
                    onClick={() => windows.remove(index)}
                  />
                </li>
              )
            })}
          </ul>
          {windowsError && (
            <p role="alert" className="text-[13px] text-signal">
              {windowsError}
            </p>
          )}
          <Button
            variant="secondary"
            size="sm"
            className="self-start"
            icon={<Plus className="size-4" aria-hidden="true" />}
            disabled={windows.fields.length >= MAX_BOOKING_WINDOWS}
            onClick={() => windows.append({ label: '', start: '10:00', end: '12:00' })}
          >
            Add window
          </Button>
        </fieldset>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Days shown ahead" hint="How many open days buyers can pick from, 1 to 30." error={errors.booking_days_ahead?.message}>
            <Input {...register('booking_days_ahead')} inputMode="numeric" autoComplete="off" className="max-w-32" />
          </Field>
          <Field label="Reminder (hours before)" hint="0 to 48. 0 sends no reminder." error={errors.booking_reminder_hours?.message}>
            <Input {...register('booking_reminder_hours')} inputMode="numeric" autoComplete="off" className="max-w-32" />
          </Field>
        </div>
      </div>
    </SectionCard>
  )
}
