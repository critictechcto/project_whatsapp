import type { ReactNode } from 'react'
import { CircleAlert, CircleCheck, Info, TriangleAlert } from 'lucide-react'
import { cn } from '../../../../lib/cn'

const tones = {
  info: { box: 'border-line bg-paper-2/60 text-ink', icon: <Info className="size-4 text-muted" aria-hidden="true" /> },
  success: { box: 'border-accent/25 bg-accent-soft/60 text-ink', icon: <CircleCheck className="size-4 text-accent" aria-hidden="true" /> },
  warning: { box: 'border-amber/25 bg-amber-soft/60 text-ink', icon: <TriangleAlert className="size-4 text-amber" aria-hidden="true" /> },
  danger: { box: 'border-signal/25 bg-signal-soft/60 text-ink', icon: <CircleAlert className="size-4 text-signal" aria-hidden="true" /> },
} as const

type NoticeProps = {
  tone?: keyof typeof tones
  title?: ReactNode
  children?: ReactNode
  /** Custom icon (e.g. a spinner for progress). */
  icon?: ReactNode
  action?: ReactNode
  /** `status` for polite live updates, `alert` for errors that need attention. */
  role?: 'status' | 'alert'
  className?: string
}

/** Inline callout for explanations, warnings and progress. Candidate for `components/app`. */
export function Notice({ tone = 'info', title, children, icon, action, role, className }: NoticeProps) {
  const style = tones[tone]
  return (
    <div role={role} className={cn('flex flex-col gap-3 rounded-lg border px-3.5 py-3 text-sm sm:flex-row sm:items-start', style.box, className)}>
      <div className="flex min-w-0 flex-1 items-start gap-2.5">
        <span className="mt-0.5 shrink-0">{icon ?? style.icon}</span>
        <div className="min-w-0">
          {title && <p className="font-medium text-ink">{title}</p>}
          {children && <div className={cn('text-[13px] text-muted', title ? 'mt-0.5' : undefined)}>{children}</div>}
        </div>
      </div>
      {action && <div className="shrink-0 sm:self-center">{action}</div>}
    </div>
  )
}
