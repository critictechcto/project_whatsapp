import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'

type PageHeaderProps = {
  title: ReactNode
  description?: ReactNode
  /** Small mono label above the title, e.g. a breadcrumb or section name. */
  eyebrow?: ReactNode
  actions?: ReactNode
  className?: string
}

export function PageHeader({ title, description, eyebrow, actions, className }: PageHeaderProps) {
  return (
    <header className={cn('flex flex-col gap-4 border-b border-line pb-5 sm:flex-row sm:items-end sm:justify-between', className)}>
      <div className="min-w-0">
        {eyebrow && <p className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">{eyebrow}</p>}
        <h1 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">{title}</h1>
        {description && <p className="mt-1.5 max-w-2xl text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}

type EmptyStateProps = {
  icon?: ReactNode
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
  className?: string
}

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center rounded-xl border border-dashed border-line px-6 py-14 text-center', className)}>
      {icon && (
        <div aria-hidden="true" className="mb-4 grid size-11 place-items-center rounded-lg border border-line bg-card text-muted [&_svg]:size-5">
          {icon}
        </div>
      )}
      <h2 className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">{title}</h2>
      {description && <p className="mt-1.5 max-w-md text-sm text-muted">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}
