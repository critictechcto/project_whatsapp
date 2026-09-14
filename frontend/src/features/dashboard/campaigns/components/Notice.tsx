import { CircleAlert, Info, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '../../../../lib/cn'

type NoticeProps = {
  tone?: 'info' | 'warning' | 'error'
  title?: ReactNode
  children?: ReactNode
  action?: ReactNode
  className?: string
}

const tones = {
  info: { box: 'border-line bg-paper-2/70 text-ink-2', icon: Info },
  warning: { box: 'border-amber/25 bg-amber-soft/70 text-amber', icon: TriangleAlert },
  error: { box: 'border-signal/25 bg-signal-soft/60 text-signal', icon: CircleAlert },
} as const

/** Inline message box. Errors are announced (`role="alert"`). */
export function Notice({ tone = 'info', title, children, action, className }: NoticeProps) {
  const Icon = tones[tone].icon
  return (
    <div
      role={tone === 'error' ? 'alert' : undefined}
      className={cn('flex items-start gap-2.5 rounded-lg border px-3.5 py-3 text-sm', tones[tone].box, className)}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className={cn(title ? "mt-0.5" : undefined, tone === "info" && "text-muted")}>{children}</div>}
        {action && <div className="mt-2">{action}</div>}
      </div>
    </div>
  )
}
