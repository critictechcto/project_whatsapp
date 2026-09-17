import { useState, type FormEvent } from 'react'
import { Button, Field, Input, Select } from '../../../../components/app'
import {
  MAX_RANGE_DAYS,
  presetOf,
  presetOptions,
  presetRange,
  validateRange,
  type RangePreset,
} from '../range'
import type { DateRange } from '../types'

type RangeControlProps = {
  range: DateRange
  today: string
  onChange: (range: DateRange) => void
}

/** Last 7 / 30 / 90 days or a custom range of at most 92 days. The page keeps the range in the URL. */
export function RangeControl({ range, today, onChange }: RangeControlProps) {
  const [customOpen, setCustomOpen] = useState(() => presetOf(range, today) === 'custom')
  const preset: RangePreset = customOpen ? 'custom' : presetOf(range, today)

  function onPresetChange(value: RangePreset) {
    if (value === 'custom') {
      setCustomOpen(true)
      return
    }
    setCustomOpen(false)
    onChange(presetRange(Number(value), today))
  }

  return (
    <div className="flex w-full flex-col gap-3 sm:w-auto sm:items-end">
      <Field label="Date range" className="w-full sm:w-52">
        <Select value={preset} options={presetOptions} onChange={(event) => onPresetChange(event.target.value as RangePreset)} />
      </Field>
      {preset === 'custom' && <CustomRangeForm key={`${range.from}:${range.to}`} range={range} today={today} onApply={onChange} />}
    </div>
  )
}

function CustomRangeForm({ range, today, onApply }: { range: DateRange; today: string; onApply: (range: DateRange) => void }) {
  const [from, setFrom] = useState(range.from)
  const [to, setTo] = useState(range.to)
  const [error, setError] = useState<string | null>(null)

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const message = validateRange({ from, to }, today)
    setError(message)
    if (!message) onApply({ from, to })
  }

  return (
    <form onSubmit={onSubmit} noValidate aria-label="Custom date range" className="flex w-full flex-col gap-2 sm:w-auto">
      <div className="grid grid-cols-2 gap-2 sm:flex sm:items-end">
        <Field label="From" className="sm:w-40">
          <Input type="date" value={from} max={today} onChange={(event) => setFrom(event.target.value)} />
        </Field>
        <Field label="To" className="sm:w-40">
          <Input type="date" value={to} max={today} onChange={(event) => setTo(event.target.value)} />
        </Field>
        <Button type="submit" variant="primary" className="col-span-2 sm:col-span-1">
          Apply
        </Button>
      </div>
      {error ? (
        <p role="alert" className="text-[13px] text-signal">
          {error}
        </p>
      ) : (
        <p className="text-[12px] text-muted">Up to {MAX_RANGE_DAYS} days.</p>
      )}
    </form>
  )
}
