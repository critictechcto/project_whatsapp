import { ChevronDown } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { cn } from '../../../../lib/cn'

type DisclosureProps = {
  title: ReactNode
  description?: ReactNode
  children: ReactNode
  defaultOpen?: boolean
}

/** A card whose body opens from its header button. Closed content isn't rendered. Candidate for `components/app`. */
export function Disclosure({ title, description, children, defaultOpen = false }: DisclosureProps) {
  const [open, setOpen] = useState(defaultOpen)
  const panelId = useId()

  return (
    <section className="rounded-xl border border-line bg-card">
      <h2 className="font-display text-base font-semibold tracking-[-0.01em] text-ink">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((value) => !value)}
          className="flex w-full items-start justify-between gap-3 rounded-xl px-5 py-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
        >
          <span className="min-w-0">
            <span className="block">{title}</span>
            {description && <span className="mt-1 block font-sans text-[13px] font-normal tracking-normal text-muted">{description}</span>}
          </span>
          <ChevronDown className={cn('mt-0.5 size-4 shrink-0 text-muted transition-transform', open && 'rotate-180')} aria-hidden="true" />
        </button>
      </h2>
      {open && (
        <div id={panelId} className="border-t border-line-2 px-5 py-4">
          {children}
        </div>
      )}
    </section>
  )
}
