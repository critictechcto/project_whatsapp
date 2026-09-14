import { Plus, Trash2 } from 'lucide-react'
import { useFieldArray, useFormContext, useWatch } from 'react-hook-form'
import { Button } from '../../../../components/app/Button'
import { Field } from '../../../../components/app/Field'
import { Input } from '../../../../components/app/Input'
import { buttonTypeLabels, emptyButton, type BuilderValues, type ButtonType } from '../lib/builderModel'
import { errorAt } from '../lib/formErrors'
import {
  BUTTON_TEXT_MAX_LENGTH,
  COPY_CODE_MAX_LENGTH,
  MAX_BUTTONS,
  MAX_COPY_CODE_BUTTONS,
  MAX_PHONE_BUTTONS,
  MAX_URL_BUTTONS,
  textLength,
  variableNumbers,
} from '../lib/validate'

const typeLimits: Record<ButtonType, number> = {
  QUICK_REPLY: MAX_BUTTONS,
  URL: MAX_URL_BUTTONS,
  PHONE_NUMBER: MAX_PHONE_BUTTONS,
  COPY_CODE: MAX_COPY_CODE_BUTTONS,
}

const addOrder: ButtonType[] = ['QUICK_REPLY', 'URL', 'PHONE_NUMBER', 'COPY_CODE']

function Counter({ value, max }: { value: string; max: number }) {
  const length = textLength(value)
  return (
    <span className={length > max ? 'text-signal' : undefined}>
      {length}/{max}
    </span>
  )
}

/** Quick replies and call-to-action buttons within Meta's limits. New buttons join their group so quick replies stay together. */
export function ButtonsEditor() {
  const {
    control,
    register,
    getValues,
    setValue,
    formState: { errors, isSubmitted },
  } = useFormContext<BuilderValues>()
  const { fields, insert, remove } = useFieldArray({ control, name: 'buttons' })
  const buttons = useWatch({ control, name: 'buttons' }) ?? []

  const count = (type: ButtonType) => buttons.filter((button) => button.type === type).length
  const full = buttons.length >= MAX_BUTTONS

  const add = (type: ButtonType) => {
    const isQuickReply = type === 'QUICK_REPLY'
    const lastInGroup = buttons.reduce((last, button, index) => ((button.type === 'QUICK_REPLY') === isQuickReply ? index : last), -1)
    insert(lastInGroup === -1 ? buttons.length : lastInGroup + 1, emptyButton(type), { shouldFocus: true })
  }

  const addUrlVariable = (index: number) => {
    const path = `buttons.${index}.url` as const
    const url = getValues(path)
    if (variableNumbers(url).length) return
    setValue(path, `${url.replace(/\/?$/, '/')}{{1}}`, { shouldDirty: true, shouldValidate: isSubmitted })
  }

  const groupError = errorAt(errors, 'buttons')

  return (
    <div className="flex flex-col gap-4">
      {fields.map((field, index) => {
        const button = buttons[index] ?? field
        const label = `Button ${index + 1}`
        const hasUrlVariable = button.type === 'URL' && variableNumbers(button.url).length > 0
        return (
          <fieldset key={field.id} className="rounded-lg border border-line bg-paper/40 p-4">
            <div className="flex items-center justify-between gap-3">
              <legend className="text-[13px] font-medium text-ink">
                {label} <span className="font-normal text-muted">· {buttonTypeLabels[button.type]}</span>
              </legend>
              <Button variant="ghost" size="icon-sm" aria-label={`Remove ${label.toLowerCase()}`} onClick={() => remove(index)}>
                <Trash2 className="size-4" aria-hidden="true" />
              </Button>
            </div>

            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {button.type !== 'COPY_CODE' && (
                <Field
                  label="Button text"
                  required
                  hint={<Counter value={button.text} max={BUTTON_TEXT_MAX_LENGTH} />}
                  error={errorAt(errors, `buttons.${index}.text`)}
                >
                  <Input {...register(`buttons.${index}.text`)} />
                </Field>
              )}

              {button.type === 'URL' && (
                <Field
                  label="Website URL"
                  required
                  hint="Starts with https://. Add {{1}} at the end for a link that changes per message, like an order id."
                  error={errorAt(errors, `buttons.${index}.url`)}
                  className="sm:col-span-2"
                >
                  <div className="flex gap-2">
                    <Input type="url" inputMode="url" placeholder="https://sharmasweets.in/track/{{1}}" className="flex-1" {...register(`buttons.${index}.url`)} />
                    <Button variant="secondary" onClick={() => addUrlVariable(index)} disabled={hasUrlVariable}>
                      Add {'{{1}}'}
                    </Button>
                  </div>
                </Field>
              )}

              {hasUrlVariable && (
                <Field
                  label="Example for {{1}}"
                  required
                  hint="Meta reviews the link with this value."
                  error={errorAt(errors, `buttons.${index}.urlExample`)}
                >
                  <Input placeholder="SS-10482" {...register(`buttons.${index}.urlExample`)} />
                </Field>
              )}

              {button.type === 'PHONE_NUMBER' && (
                <Field
                  label="Phone number"
                  required
                  hint="With country code, e.g. +919829011223."
                  error={errorAt(errors, `buttons.${index}.phoneNumber`)}
                >
                  <Input type="tel" inputMode="tel" placeholder="+919829011223" {...register(`buttons.${index}.phoneNumber`)} />
                </Field>
              )}

              {button.type === 'COPY_CODE' && (
                <Field
                  label="Sample offer code"
                  required
                  hint={
                    <>
                      <Counter value={button.code} max={COPY_CODE_MAX_LENGTH} /> · Customers tap to copy the code. You set the real code when sending.
                    </>
                  }
                  error={errorAt(errors, `buttons.${index}.code`)}
                  className="sm:col-span-2"
                >
                  <Input placeholder="DIWALI26" {...register(`buttons.${index}.code`)} />
                </Field>
              )}
            </div>
          </fieldset>
        )
      })}

      {groupError && (
        <p role="alert" className="text-[13px] text-signal">
          {groupError}
        </p>
      )}

      <div>
        <p className="text-[13px] text-muted" id="button-limits">
          {buttons.length}/{MAX_BUTTONS} buttons. Up to {MAX_URL_BUTTONS} website buttons, {MAX_PHONE_BUTTONS} phone button and {MAX_COPY_CODE_BUTTONS} offer code
          button. Quick replies stay grouped together.
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          {addOrder.map((type) => (
            <Button
              key={type}
              variant="secondary"
              size="sm"
              icon={<Plus className="size-3.5" aria-hidden="true" />}
              disabled={full || count(type) >= typeLimits[type]}
              aria-describedby="button-limits"
              onClick={() => add(type)}
            >
              {buttonTypeLabels[type]}
            </Button>
          ))}
        </div>
      </div>
    </div>
  )
}
