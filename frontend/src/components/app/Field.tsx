import { useId, type LabelHTMLAttributes, type ReactNode } from 'react'
import { cn } from '../../lib/cn'
import { FieldContext } from './fieldContext'

export function Label({ className, children, ...props }: LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label className={cn('text-[13px] font-medium text-ink', className)} {...props}>
      {children}
    </label>
  )
}

export function FieldError({ id, children }: { id?: string; children?: ReactNode }) {
  if (!children) return null
  return (
    <p id={id} className="text-[13px] text-signal">
      {children}
    </p>
  )
}

type FieldProps = {
  label: ReactNode
  /** Help text under the control. */
  hint?: ReactNode
  /** Error message; marks the control `aria-invalid`. */
  error?: ReactNode
  required?: boolean
  /** Hide the label visually (still read by screen readers). */
  hideLabel?: boolean
  className?: string
  children: ReactNode
}

/**
 * Label + control + hint + error. Controls from this kit (`Input`, `Textarea`, `Select`, `Combobox`,
 * `DateTimePicker`) pick up the id and aria attributes automatically:
 *
 * ```tsx
 * <Field label="Email" error={errors.email?.message}>
 *   <Input type="email" {...register('email')} />
 * </Field>
 * ```
 */
export function Field({ label, hint, error, required = false, hideLabel = false, className, children }: FieldProps) {
  const id = useId()
  const hintId = hint ? `${id}-hint` : undefined
  const errorId = error ? `${id}-error` : undefined
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined

  return (
    <FieldContext.Provider value={{ id, describedBy, invalid: Boolean(error), required }}>
      <div className={cn('flex flex-col gap-1.5', className)}>
        <Label htmlFor={id} className={hideLabel ? 'sr-only' : undefined}>
          {label}
          {required && (
            <span aria-hidden="true" className="ml-0.5 text-signal">
              *
            </span>
          )}
        </Label>
        {children}
        {hint && (
          <p id={hintId} className="text-[13px] text-muted">
            {hint}
          </p>
        )}
        <FieldError id={errorId}>{error}</FieldError>
      </div>
    </FieldContext.Provider>
  )
}
