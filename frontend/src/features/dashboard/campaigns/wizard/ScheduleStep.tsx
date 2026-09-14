import { useState } from 'react'
import { useFormContext, useWatch } from 'react-hook-form'
import { DateTimePicker, Field } from '../../../../components/app'
import { timeZoneName } from '../../../../lib/datetime'
import { useWorkspace } from '../../../../lib/workspace'
import { currentIso } from '../clock'
import { Notice } from '../components/Notice'
import { RadioCards } from '../components/RadioCards'
import type { WizardValues } from '../wizardSchema'

export function ScheduleStep() {
  const {
    control,
    setValue,
    formState: { errors },
  } = useFormContext<WizardValues>()
  const { timeZone } = useWorkspace()
  const schedule = useWatch({ control, name: 'schedule' })
  const [min] = useState(currentIso)
  const zone = timeZoneName(timeZone)
  const scheduleError = errors.schedule?.at?.message

  const update = (patch: Partial<WizardValues['schedule']>) =>
    setValue('schedule', { ...schedule, ...patch }, { shouldDirty: true, shouldValidate: Boolean(scheduleError) })

  return (
    <div className="flex max-w-2xl flex-col gap-5">
      <RadioCards
        legend="When to send"
        value={schedule.mode}
        onChange={(mode) => update({ mode })}
        options={[
          { value: 'now', label: 'Send now', description: 'Sending starts as soon as you launch.' },
          { value: 'later', label: 'Schedule', description: `Pick a date and time in ${zone}.` },
        ]}
      />

      {schedule.mode === 'later' && (
        <Field label="Send at" hint={`Workspace time zone: ${zone} (${timeZone})`} error={scheduleError} required>
          <DateTimePicker value={schedule.at} onChange={(at) => update({ at })} min={min} timeZone={timeZone} aria-invalid={Boolean(scheduleError)} />
        </Field>
      )}

      <Notice title="Large audiences send gradually">
        Meta limits how many people a number can start conversations with in 24 hours, based on its messaging limit and quality rating.
        Big campaigns may take a while to finish, and we pause sending if Meta reports a problem with your number.
      </Notice>
    </div>
  )
}
