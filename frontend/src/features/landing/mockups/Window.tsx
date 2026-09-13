import type { ReactNode } from 'react'
import { cn } from '../../../lib/cn'

export const mockShadow = 'shadow-[0_1px_0_rgba(16,39,31,0.04),0_28px_56px_-28px_rgba(16,39,31,0.28)]'

type WindowProps = {
  title: string
  right?: ReactNode
  className?: string
  children: ReactNode
}

/** App-window frame used by the product mockups. Decorative, so hidden from assistive tech. */
export function Window({ title, right, className, children }: WindowProps) {
  return (
    <div aria-hidden="true" className={cn('overflow-hidden rounded-xl border border-line bg-card', mockShadow, className)}>
      <div className="flex h-10 items-center gap-3 border-b border-line-2 bg-paper/70 px-4">
        <div className="flex gap-1.5">
          <span className="size-2.5 rounded-full bg-line" />
          <span className="size-2.5 rounded-full bg-line" />
          <span className="size-2.5 rounded-full bg-line" />
        </div>
        <p className="truncate font-mono text-[11px] text-muted">{title}</p>
        {right && <div className="ml-auto shrink-0">{right}</div>}
      </div>
      {children}
    </div>
  )
}
