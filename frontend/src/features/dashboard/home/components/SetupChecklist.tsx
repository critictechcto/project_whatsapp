import { ArrowRight, ChevronDown, Circle, CircleCheck, CircleHelp } from 'lucide-react'
import { useId, useState } from 'react'
import { Link } from 'react-router'
import { Skeleton } from '../../../../components/app'
import { cn } from '../../../../lib/cn'
import { usePrefersReducedMotion } from '../../../../lib/motion'
import './checklist.css'

export type StepState = 'loading' | 'done' | 'todo' | 'unknown'

export type SetupStep = {
  id: string
  title: string
  description: string
  /** One line on why the step matters for the workspace's goal. */
  why?: string
  to: string
  cta: string
  state: StepState
}

function StepIcon({ state, pop }: { state: StepState; pop: boolean }) {
  if (state === 'loading') return <Skeleton className="size-5 rounded-full" />
  if (state === 'done') return <CircleCheck className={cn('size-5 text-accent', pop && 'check-pop')} aria-label="Done" />
  if (state === 'unknown') return <CircleHelp className="size-5 text-muted" aria-label="Couldn't check" />
  return <Circle className="size-5 text-line" aria-label="Not done" />
}

const stateKey = (steps: readonly SetupStep[]) => steps.map((step) => `${step.id}:${step.state}`).join('|')

/**
 * Steps that turned done while the page was open (from "todo" or "couldn't check", never from
 * loading), so only real progress pops a check.
 */
function useNewlyDone(steps: readonly SetupStep[]): ReadonlySet<string> {
  const key = stateKey(steps)
  const [previous, setPrevious] = useState(() => ({ key, states: new Map(steps.map((step) => [step.id, step.state])) }))
  const [popped, setPopped] = useState<ReadonlySet<string>>(() => new Set())
  if (previous.key !== key) {
    const next = new Set(popped)
    for (const step of steps) {
      const before = previous.states.get(step.id)
      if (step.state === 'done' && (before === 'todo' || before === 'unknown')) next.add(step.id)
      if (step.state !== 'done') next.delete(step.id)
    }
    setPrevious({ key, states: new Map(steps.map((step) => [step.id, step.state])) })
    setPopped(next)
  }
  return popped
}

type Props = {
  steps: SetupStep[]
  /** Shows a "Hide checklist" button. */
  onHide?: () => void
}

/** Getting-started steps computed from real data. Collapses once every step is done. */
export function SetupChecklist({ steps, onHide }: Props) {
  const headingId = useId()
  const listId = useId()
  const reducedMotion = usePrefersReducedMotion()
  const completed = steps.filter((step) => step.state === 'done').length
  const loading = steps.some((step) => step.state === 'loading')
  const allDone = steps.length > 0 && completed === steps.length
  const [expandedOverride, setExpandedOverride] = useState<boolean | null>(null)
  const expanded = expandedOverride ?? !allDone
  const popped = useNewlyDone(steps)
  const percent = steps.length ? (completed / steps.length) * 100 : 0

  return (
    <section aria-labelledby={headingId} className="setup-checklist rounded-xl border border-line bg-card">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5">
        <div className="min-w-0">
          <h2 id={headingId} className="font-display text-base font-semibold tracking-[-0.01em] text-ink">
            {allDone ? "You're all set" : 'Get started'}
          </h2>
          {allDone && (
            <p className={cn('mt-0.5 text-[13px] text-muted', !reducedMotion && 'fade-up')}>
              Every setup step is done. Your workspace is ready for customers.
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {loading ? (
            <Skeleton className="h-4 w-20" />
          ) : (
            <p className="mr-1 font-mono text-[12px] text-muted">
              {completed} of {steps.length} done
            </p>
          )}
          {allDone && (
            <button
              type="button"
              aria-expanded={expanded}
              aria-controls={listId}
              onClick={() => setExpandedOverride(!expanded)}
              className="touch-target inline-flex items-center gap-1 rounded-md px-2 py-1 text-[13px] font-medium text-ink-2 hover:bg-paper"
            >
              {expanded ? 'Hide steps' : 'Show steps'}
              <ChevronDown className={cn('size-4 transition-transform', expanded && 'rotate-180')} aria-hidden="true" />
            </button>
          )}
          {onHide && (
            <button
              type="button"
              onClick={onHide}
              className="touch-target inline-flex items-center rounded-md px-2 py-1 text-[13px] font-medium text-muted hover:bg-paper hover:text-ink"
            >
              Hide checklist
            </button>
          )}
        </div>
      </div>
      <div
        className="h-1 overflow-hidden bg-line-2"
        role="progressbar"
        aria-label="Setup progress"
        aria-valuemin={0}
        aria-valuemax={steps.length}
        aria-valuenow={completed}
      >
        <div
          className={cn('h-full bg-accent', !reducedMotion && 'checklist-bar')}
          data-testid="setup-progress-fill"
          style={{ width: `${percent}%` }}
        />
      </div>
      <ol id={listId} hidden={!expanded} className="divide-y divide-line-2">
        {steps.map((step) => (
          <li key={step.id} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
            <span className="flex shrink-0 items-center">
              <StepIcon state={step.state} pop={!reducedMotion && popped.has(step.id)} />
            </span>
            <div className="min-w-0 flex-1">
              <p className={cn('text-sm font-medium', step.state === 'done' ? 'text-muted' : 'text-ink')}>{step.title}</p>
              {step.why && <p className="mt-0.5 text-[13px] text-ink-2">{step.why}</p>}
              <p className="mt-0.5 text-[12.5px] text-muted">{step.description}</p>
            </div>
            {step.state !== 'done' && (
              <Link
                to={step.to}
                className="inline-flex min-h-11 items-center gap-1 text-sm font-medium text-accent-2 underline-offset-2 hover:underline sm:min-h-0"
              >
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
