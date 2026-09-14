import { Field, Input, Select } from '../../../../components/app'
import type { VariableSource, VariableSourceType } from '../api'
import { contactFieldOptions, sourceTypeOptions } from '../variables'

type VariableSourceFieldsProps = {
  /** Legend, e.g. "Body {{1}}". */
  label: string
  value: VariableSource | null | undefined
  onChange: (value: VariableSource) => void
  errors?: { value?: string; fallback?: string }
  /** Sample value from the template, shown as a placeholder for fixed text. */
  example?: string
  disabled?: boolean
}

/** Where one template variable gets its value: a contact field, a contact attribute or fixed text, plus a fallback. */
export function VariableSourceFields({ label, value, onChange, errors = {}, example, disabled }: VariableSourceFieldsProps) {
  const current: VariableSource = value ?? { source: 'static', value: '', fallback: '' }

  const changeSource = (source: VariableSourceType) => {
    onChange({ source, value: source === 'contact_field' ? 'name' : '', fallback: current.fallback })
  }

  return (
    <fieldset disabled={disabled} className="rounded-lg border border-line-2 bg-card px-3.5 pb-3.5 pt-1">
      <legend className="px-1 font-mono text-[12px] text-ink">{label}</legend>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Source">
          <Select
            value={current.source}
            options={sourceTypeOptions}
            onChange={(event) => changeSource(event.target.value as VariableSourceType)}
          />
        </Field>

        {current.source === 'contact_field' && (
          <Field label="Field" error={errors.value} required>
            <Select
              value={current.value}
              options={contactFieldOptions}
              onChange={(event) => onChange({ ...current, value: event.target.value })}
            />
          </Field>
        )}
        {current.source === 'attribute' && (
          <Field label="Attribute key" error={errors.value} required>
            <Input value={current.value} placeholder="city" onChange={(event) => onChange({ ...current, value: event.target.value })} />
          </Field>
        )}
        {current.source === 'static' && (
          <Field label="Text" error={errors.value} required className="sm:col-span-2">
            <Input value={current.value} placeholder={example} onChange={(event) => onChange({ ...current, value: event.target.value })} />
          </Field>
        )}

        {current.source !== 'static' && (
          <Field label="Fallback" error={errors.fallback} required>
            <Input
              value={current.fallback}
              placeholder="Used when the contact has no value"
              onChange={(event) => onChange({ ...current, fallback: event.target.value })}
            />
          </Field>
        )}
      </div>
    </fieldset>
  )
}
