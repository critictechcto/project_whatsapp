import { useRef, type KeyboardEvent, type ReactNode } from 'react'
import { cn } from '../../../../lib/cn'

export type SegmentOption<V extends string> = { value: V; label: ReactNode; hint?: ReactNode }

type SegmentedControlProps<V extends string> = {
  /** Accessible name of the radio group. */
  label: string
  options: readonly SegmentOption<V>[]
  value: V
  onValueChange: (value: V) => void
  className?: string
}

/** Radio group styled as a segmented switch. Arrow keys move and select. Candidate for `components/app`. */
export function SegmentedControl<V extends string>({ label, options, value, onValueChange, className }: SegmentedControlProps<V>) {
  const refs = useRef<Array<HTMLButtonElement | null>>([])

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = options.findIndex((option) => option.value === value)
    let next: number | null = null
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % options.length
    if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index - 1 + options.length) % options.length
    if (next === null) return
    event.preventDefault()
    onValueChange(options[next].value)
    refs.current[next]?.focus()
  }

  return (
    <div
      role="radiogroup"
      aria-label={label}
      onKeyDown={onKeyDown}
      className={cn('inline-flex rounded-lg border border-line bg-paper-2/70 p-1', className)}
    >
      {options.map((option, index) => {
        const checked = option.value === value
        return (
          <button
            key={option.value}
            ref={(node) => {
              refs.current[index] = node
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            onClick={() => onValueChange(option.value)}
            className={cn(
              'inline-flex h-8 items-center gap-2 rounded-md px-3 text-sm font-medium transition-colors',
              checked ? 'bg-card text-ink shadow-sm ring-1 ring-line' : 'text-muted hover:text-ink',
            )}
          >
            {option.label}
            {option.hint && <span className="font-mono text-[11px] text-accent-2">{option.hint}</span>}
          </button>
        )
      })}
    </div>
  )
}
