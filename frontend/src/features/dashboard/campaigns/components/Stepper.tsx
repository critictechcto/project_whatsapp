import { Check } from 'lucide-react'
import { cn } from '../../../../lib/cn'

type StepperProps = {
  label: string
  steps: readonly { id: string; label: string }[]
  current: number
  onSelect: (index: number) => void
  disabled?: boolean
}

/** Numbered steps: a vertical list on small screens, a row from `md`. The current step has `aria-current="step"`. */
export function Stepper({ label, steps, current, onSelect, disabled }: StepperProps) {
  return (
    <nav aria-label={label}>
      <ol className="flex flex-col gap-1 md:flex-row md:gap-2">
        {steps.map((step, index) => {
          const state = index < current ? 'done' : index === current ? 'current' : 'upcoming'
          return (
            <li key={step.id} className="md:flex-1">
              <button
                type="button"
                onClick={() => onSelect(index)}
                disabled={disabled}
                aria-current={state === 'current' ? 'step' : undefined}
                className={cn(
                  'flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-colors',
                  'hover:bg-ink/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-wait',
                  state === 'current' ? 'bg-card font-medium text-ink ring-1 ring-line' : 'text-muted',
                )}
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    'flex size-6 shrink-0 items-center justify-center rounded-full font-mono text-[12px]',
                    state === 'done' && 'bg-accent text-white',
                    state === 'current' && 'bg-ink text-paper',
                    state === 'upcoming' && 'border border-line bg-card',
                  )}
                >
                  {state === 'done' ? <Check className="size-3.5" /> : index + 1}
                </span>
                <span>{step.label}</span>
                {state === 'done' && <span className="sr-only">(done)</span>}
              </button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
