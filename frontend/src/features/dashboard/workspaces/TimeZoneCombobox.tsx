import { useMemo } from 'react'
import { Combobox } from '../../../components/app'
import { timeZoneOptions } from './timeZones'

type TimeZoneComboboxProps = {
  value: string
  onChange: (zone: string) => void
  onBlur?: () => void
  disabled?: boolean
}

/** Searchable IANA time-zone picker. Put it inside a `<Field>` for the label. */
export function TimeZoneCombobox({ value, onChange, onBlur, disabled }: TimeZoneComboboxProps) {
  const options = useMemo(() => timeZoneOptions(), [])
  return (
    <div onBlur={onBlur}>
      <Combobox
        options={options}
        value={value || null}
        onChange={(next) => {
          if (next) onChange(next)
        }}
        placeholder="Search by city or region"
        emptyText="No time zone matches that search"
        selectedLabels={value ? { [value]: value } : undefined}
        disabled={disabled}
      />
    </div>
  )
}
