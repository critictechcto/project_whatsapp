import type { MessageTemplate } from '../../../api/types'
import { Field } from '../Field'
import { Input } from '../Input'
import { templatePreview, templateVariables, type TemplateVariableValues } from './template'
import { WhatsAppMessagePreview } from './WhatsAppMessagePreview'

type TemplateVariableFormProps = {
  template: Pick<MessageTemplate, 'components' | 'name'>
  value: TemplateVariableValues
  onChange: (value: TemplateVariableValues) => void
  /** Errors keyed like `body.0`, `header.0`, `buttons.1` (matches `SendMessageRequest` details after mapping). */
  errors?: Partial<Record<string, string>>
  showPreview?: boolean
  disabled?: boolean
}

function setAt(list: readonly string[], index: number, value: string, length: number) {
  const next = Array.from({ length }, (_, i) => list[i] ?? '')
  next[index] = value
  return next
}

/**
 * Inputs for every template variable with a live preview. Controlled; use with react-hook-form's
 * `Controller`. Send with `toSendParams(value)`.
 */
export function TemplateVariableForm({ template, value, onChange, errors = {}, showPreview = true, disabled }: TemplateVariableFormProps) {
  const spec = templateVariables(template)
  const hasVariables = spec.header.names.length + spec.body.names.length + spec.buttons.length > 0

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,20rem)]">
      <div className="flex flex-col gap-4">
        {!hasVariables && <p className="text-sm text-muted">This template has no variables.</p>}

        {spec.header.names.map((name, i) => (
          <Field key={`header-${name}`} label={`Header {{${name}}}`} error={errors[`header.${i}`]} required>
            <Input
              value={value.header[i] ?? ''}
              placeholder={spec.header.examples[i]}
              disabled={disabled}
              onChange={(event) => onChange({ ...value, header: setAt(value.header, i, event.target.value, spec.header.names.length) })}
            />
          </Field>
        ))}

        {spec.body.names.map((name, i) => (
          <Field key={`body-${name}`} label={`Body {{${name}}}`} error={errors[`body.${i}`]} required>
            <Input
              value={value.body[i] ?? ''}
              placeholder={spec.body.examples[i]}
              disabled={disabled}
              onChange={(event) => onChange({ ...value, body: setAt(value.body, i, event.target.value, spec.body.names.length) })}
            />
          </Field>
        ))}

        {spec.buttons.map((button) => (
          <Field
            key={`button-${button.index}`}
            label={`Button “${button.text}” URL suffix`}
            hint="Appended to the button's URL."
            error={errors[`buttons.${button.index}`]}
            required
          >
            <Input
              value={value.buttons[String(button.index)] ?? ''}
              placeholder={button.example}
              disabled={disabled}
              onChange={(event) => onChange({ ...value, buttons: { ...value.buttons, [String(button.index)]: event.target.value } })}
            />
          </Field>
        ))}
      </div>

      {showPreview && <WhatsAppMessagePreview message={templatePreview(template, value)} className="self-start" />}
    </div>
  )
}
