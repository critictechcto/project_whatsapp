import { useId, type ReactNode } from 'react'
import { cn } from '../../../../lib/cn'

type SectionCardProps = {
  title: ReactNode
  /** Small content at the right of the title, e.g. a count or a link. */
  aside?: ReactNode
  children: ReactNode
  className?: string
}

/** A titled card; exposed as a region named by its title. */
export function SectionCard({ title, aside, children, className }: SectionCardProps) {
  const headingId = useId()
  return (
    <section aria-labelledby={headingId} className={cn('rounded-xl border border-line bg-card', className)}>
      <div className="flex items-center justify-between gap-3 border-b border-line-2 px-4 py-3 sm:px-5">
        <h2 id={headingId} className="font-display text-[15px] font-semibold tracking-[-0.01em] text-ink">
          {title}
        </h2>
        {aside && <div className="text-[13px] text-muted">{aside}</div>}
      </div>
      <div className="px-4 py-4 sm:px-5">{children}</div>
    </section>
  )
}

/** Label/value rows inside a card. */
export function DetailList({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="flex flex-col gap-2.5 text-sm">
      {items.map((item) => (
        <div key={item.label} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5">
          <dt className="text-[13px] text-muted">{item.label}</dt>
          <dd className="min-w-0 text-right text-ink">{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}
