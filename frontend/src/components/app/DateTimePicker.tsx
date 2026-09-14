import { useId, useState } from 'react'
import { fromZonedParts, timeZoneName, toZonedParts } from '../../lib/datetime'
import { useOptionalWorkspace } from '../../lib/workspace'
import { useFieldControl } from './fieldContext'
import { controlClasses } from './styles'
import { cn } from '../../lib/cn'

type DateTimePickerProps = {
  /** UTC ISO string or null. */
  value: string | null
  onChange: (value: string | null) => void
  /** IANA zone; defaults to the current workspace's zone. */
  timeZone?: string
  /** Earliest allowed instant (UTC ISO), e.g. now for scheduling. */
  min?: string
  disabled?: boolean
  id?: string
  'aria-describedby'?: string
  'aria-invalid'?: boolean
  className?: string
}

/**
 * Date + time inputs in the workspace time zone; emits UTC ISO strings.
 * The date input takes the `<Field>` id so the field label points at it.
 */
export function DateTimePicker(rawProps: DateTimePickerProps) {
  const props = useFieldControl(rawProps)
  const workspace = useOptionalWorkspace()
  const timeZone = props.timeZone ?? workspace?.timeZone ?? 'Asia/Kolkata'
  const timeId = useId()

  const initial = props.value ? toZonedParts(props.value, timeZone) : { date: '', time: '' }
  const [draft, setDraft] = useState(initial)
  const [lastValue, setLastValue] = useState(props.value)

  // Sync from outside when the value changes (e.g. form reset).
  if (props.value !== lastValue) {
    setLastValue(props.value)
    setDraft(props.value ? toZonedParts(props.value, timeZone) : { date: '', time: '' })
  }

  const min = props.min ? toZonedParts(props.min, timeZone) : null

  const update = (next: { date: string; time: string }) => {
    const withDefaultTime = next.date && !next.time ? { ...next, time: '10:00' } : next
    setDraft(withDefaultTime)
    const iso = withDefaultTime.date ? fromZonedParts(withDefaultTime.date, withDefaultTime.time, timeZone) : null
    setLastValue(iso)
    props.onChange(iso)
  }

  return (
    <div className={cn('flex flex-wrap items-center gap-2', props.className)}>
      <input
        type="date"
        id={props.id}
        aria-describedby={props['aria-describedby']}
        aria-invalid={props['aria-invalid'] || undefined}
        disabled={props.disabled}
        min={min?.date}
        value={draft.date}
        onChange={(event) => update({ ...draft, date: event.target.value })}
        className={cn(controlClasses, 'h-10 w-auto')}
      />
      <label htmlFor={timeId} className="sr-only">
        Time
      </label>
      <input
        type="time"
        id={timeId}
        aria-describedby={props['aria-describedby']}
        disabled={props.disabled || !draft.date}
        value={draft.time}
        step={60}
        onChange={(event) => update({ ...draft, time: event.target.value })}
        className={cn(controlClasses, 'h-10 w-auto')}
      />
      <span className="font-mono text-[12px] text-muted">
        {timeZoneName(timeZone)} · {timeZone}
      </span>
    </div>
  )
}
