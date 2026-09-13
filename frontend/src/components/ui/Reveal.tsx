import type { CSSProperties, ReactNode } from 'react'
import { cn } from '../../lib/cn'
import { useInView } from '../../lib/useInView'

type RevealProps = {
  as?: 'div' | 'li' | 'ol' | 'ul' | 'article' | 'aside'
  /** Stagger offset in milliseconds. */
  delay?: number
  className?: string
  children: ReactNode
}

/** Fades and lifts its content in the first time it scrolls into view. Styles live in index.css (.reveal). */
export function Reveal({ as = 'div', delay = 0, className, children }: RevealProps) {
  const { ref, inView } = useInView<HTMLDivElement>()
  // Every allowed tag accepts the same props; narrowing to one keeps the ref type simple.
  const Component = as as 'div'

  return (
    <Component
      ref={ref}
      className={cn('reveal', inView && 'is-visible', className)}
      style={{ '--reveal-delay': `${delay}ms` } as CSSProperties}
    >
      {children}
    </Component>
  )
}
