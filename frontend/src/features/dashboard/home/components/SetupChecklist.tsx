import { ArrowRight, ChevronDown, Circle, CircleCheck, CircleHelp } from 'lucide-react'
import { useId, useState } from 'react'
import { Link } from 'react-router'
import { Skeleton } from '../../../../components/app'
import { cn } from '../../../../lib/cn'

export type StepState = 'loading' | 'done' | 'todo' | 'unknown'

export type SetupStep = {
  id: string
  title: string
  description: string
  to: string
  cta: string
  state: StepState
}

function StepIcon({ state }: { state: StepState }) {
  if (state === 'loading') return <Skeleton className="size-5 rounded-full" />
  if (state === 'done') return <CircleCheck className="size-5 text-accent" aria-label="Done" />
  if (state === 'unknown') return <CircleHelp className="size-5 text-muted" aria-label="Couldn't check" />
  return <Circle className="size-5 text-line" aria-label="Not done" />
}

/** Getting-started steps computed from real data. Collapses once every step is done. */
export function SetupChecklist({ steps }: { steps: SetupStep[] }) {
  const headingId = useId()
  const listId = useId()
  const completed = steps.filter((step) => step.state === 'done').length
  const loading = steps.some((step) => step.state === 'loading')
  const allDone = completed === steps.length
  const [expandedOverride, setExpandedOverride] = useState<boolean | null>(null)
  const expanded = expandedOverride ?? !allDone

  return (
    <section aria-labelledby={headingId} className="rounded-xl border border-line bg-card">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5">
        <div className="min-w-0">
          <h2 id={headingId} className="font-display text-base font-semibold tracking-[-0.01em] text-ink">
            {allDone ? 'Setup complete' : 'Get started'}
          </h2>
          {allDone && <p className="mt-0.5 text-[13px] text-muted">Every setup step is done. You can reopen the list any time.</p>}
        </div>
        <div className="flex items-center gap-3">
          {loading ? (
            <Skeleton className="h-4 w-20" />
          ) : (
            <p className="font-mono text-[12px] text-muted">
              {completed} of {steps.length} done
            </p>
          )}
          {allDone && (
            <button
              type="button"
              aria-expanded={expanded}
              aria-controls={listId}
              onClick={() => setExpandedOverride(!expanded)}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[13px] font-medium text-ink-2 hover:bg-paper"
            >
              {expanded ? 'Hide steps' : 'Show steps'}
              <ChevronDown className={cn('size-4 transition-transform', expanded && 'rotate-180')} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
      <div
        className="h-1 bg-line-2"
        role="progressbar"
        aria-label="Setup progress"
        aria-valuemin={0}
        aria-valuemax={steps.length}
        aria-valuenow={completed}
      >
        <div className="h-full bg-accent transition-[width]" style={{ width: `${(completed / steps.length) * 100}%` }} />
      </div>
      <ol id={listId} hidden={!expanded} className="divide-y divide-line-2">
        {steps.map((step) => (
          <li key={step.id} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
            <span className="flex shrink-0 items-center">
              <StepIcon state={step.state} />
            </span>
            <div className="min-w-0 flex-1">
              <p className={cn('text-sm font-medium', step.state === 'done' ? 'text-muted' : 'text-ink')}>{step.title}</p>
              <p className="mt-0.5 text-[13px] text-muted">{step.description}</p>
            </div>
            {step.state !== 'done' && (
              <Link to={step.to} className="inline-flex items-center gap-1 text-sm font-medium text-accent-2 underline-offset-2 hover:underline">
                {step.cta}
                <ArrowRight className="size-3.5" aria-hidden="true" />
              </Link>
            )}
          </li>
        ))}
      </ol>
    </section>
  )
}
