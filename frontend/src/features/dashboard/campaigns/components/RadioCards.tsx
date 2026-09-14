import { useId, type ReactNode } from 'react'
import { cn } from '../../../../lib/cn'

export type RadioCardOption<V extends string> = { value: V; label: ReactNode; description?: ReactNode; disabled?: boolean }

type RadioCardsProps<V extends string> = {
  legend: ReactNode
  value: V
  onChange: (value: V) => void
  options: readonly RadioCardOption<V>[]
  disabled?: boolean
  columns?: 1 | 2 | 4
  hideLegend?: boolean
  error?: string
  className?: string
}

const gridColumns = { 1: '', 2: 'sm:grid-cols-2', 4: 'sm:grid-cols-2 lg:grid-cols-4' } as const

/** Native radio group styled as selectable cards (arrow keys move between options). */
export function RadioCards<V extends string>({
  legend,
  value,
  onChange,
  options,
  disabled,
  columns = 2,
  hideLegend,
  error,
  className,
}: RadioCardsProps<V>) {
  const name = useId()
  const errorId = `${name}-error`
  return (
    <fieldset className={cn('flex flex-col gap-2', className)} disabled={disabled} aria-describedby={error ? errorId : undefined}>
      <legend className={cn('mb-1.5 text-[13px] font-medium text-ink', hideLegend && 'sr-only')}>{legend}</legend>
      <div className={cn('grid gap-2', gridColumns[columns])}>
        {options.map((option) => {
          const checked = option.value === value
          return (
            <label
              key={option.value}
              className={cn(
                'flex cursor-pointer items-start gap-2.5 rounded-lg border bg-card px-3.5 py-3 transition-colors',
                checked ? 'border-accent ring-1 ring-accent/30' : 'border-line hover:border-ink/30',
                (disabled || option.disabled) && 'cursor-not-allowed opacity-60',
              )}
            >
              <input
                type="radio"
                name={name}
                value={option.value}
                checked={checked}
                disabled={option.disabled}
                onChange={() => onChange(option.value)}
                className="mt-0.5 size-4 shrink-0 accent-accent"
              />
              <span className="min-w-0 text-sm leading-5">
                <span className="block font-medium text-ink">{option.label}</span>
                {option.description && <span className="mt-0.5 block text-[13px] text-muted">{option.description}</span>}
              </span>
            </label>
          )
        })}
      </div>
      {error && (
        <p id={errorId} className="text-[13px] text-signal">
          {error}
        </p>
      )}
    </fieldset>
  )
}
