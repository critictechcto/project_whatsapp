import { useId, type InputHTMLAttributes, type ReactNode, type Ref } from 'react'
import { cn } from '../../lib/cn'

export type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & {
  label: ReactNode
  description?: ReactNode
  ref?: Ref<HTMLInputElement>
}

export function Checkbox({ label, description, className, id, ref, ...props }: CheckboxProps) {
  const autoId = useId()
  const inputId = id ?? autoId
  const descriptionId = description ? `${inputId}-description` : undefined

  return (
    <div className={cn('flex items-start gap-2.5', className)}>
      <input
        ref={ref}
        id={inputId}
        type="checkbox"
        aria-describedby={descriptionId}
        className="mt-0.5 size-4 shrink-0 cursor-pointer rounded border-line accent-accent disabled:cursor-not-allowed"
        {...props}
      />
      <div className="text-sm leading-5">
        <label htmlFor={inputId} className="cursor-pointer text-ink">
          {label}
        </label>
        {description && (
          <p id={descriptionId} className="text-[13px] text-muted">
            {description}
          </p>
        )}
      </div>
    </div>
  )
}

type SwitchProps = {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  label: ReactNode
  description?: ReactNode
  disabled?: boolean
  /** Visually hide the label. */
  hideLabel?: boolean
  className?: string
}

/** On/off toggle with `role="switch"`. Space and Enter toggle it (native button behaviour). */
export function Switch({ checked, onCheckedChange, label, description, disabled, hideLabel, className }: SwitchProps) {
  const id = useId()
  return (
    <div className={cn('flex items-start justify-between gap-4', className)}>
      <div className={cn('text-sm leading-5', hideLabel && 'sr-only')}>
        <span id={`${id}-label`} className="text-ink">
          {label}
        </span>
        {description && (
          <p id={`${id}-description`} className="text-[13px] text-muted">
            {description}
          </p>
        )}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={`${id}-label`}
        aria-describedby={description ? `${id}-description` : undefined}
        disabled={disabled}
        onClick={() => onCheckedChange(!checked)}
        className={cn(
          'relative inline-flex h-6 w-10 shrink-0 items-center rounded-full border transition-colors disabled:cursor-not-allowed disabled:opacity-50',
          checked ? 'border-accent bg-accent' : 'border-line bg-paper-2',
        )}
      >
        <span
          aria-hidden="true"
          className={cn(
            'inline-block size-4.5 rounded-full bg-white shadow-sm transition-transform',
            checked ? 'translate-x-[18px]' : 'translate-x-[3px]',
          )}
        />
      </button>
    </div>
  )
}
