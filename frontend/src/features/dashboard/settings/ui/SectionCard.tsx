import type { ReactNode } from 'react'
import { cn } from '../../../../lib/cn'

type SectionCardProps = {
  title: ReactNode
  description?: ReactNode
  /** Buttons or links in the header, right-aligned on wide screens. */
  actions?: ReactNode
  children?: ReactNode
  footer?: ReactNode
  className?: string
  /** Visually marks destructive sections (e.g. deleting a workspace). */
  tone?: 'default' | 'danger'
  id?: string
}

/**
 * Card with a titled header, used by settings, team, WhatsApp and billing screens.
 * Candidate for `components/app`.
 */
export function SectionCard({ title, description, actions, children, footer, className, tone = 'default', id }: SectionCardProps) {
  const headingId = id ? `${id}-heading` : undefined
  return (
    <section
      aria-labelledby={headingId}
      className={cn('rounded-xl border bg-card', tone === 'danger' ? 'border-signal/30' : 'border-line', className)}
    >
      <div className="flex flex-col gap-3 border-b border-line-2 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 id={headingId} className="font-display text-base font-semibold tracking-[-0.01em] text-ink">
            {title}
          </h2>
          {description && <p className="mt-1 text-[13px] text-muted">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children && <div className="px-5 py-4">{children}</div>}
      {footer && <div className="flex flex-wrap items-center justify-end gap-2 border-t border-line-2 px-5 py-3">{footer}</div>}
    </section>
  )
}
