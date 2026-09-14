import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'
import { useInView } from '../../lib/useInView'

/**
 * Tips its content back slightly and lays it flat as it scrolls into view.
 * Uses a CSS scroll-driven animation where supported and an in-view transition elsewhere
 * (styles in index.css, .scroll-depth). Reduced motion shows the content flat.
 *
 * Put it inside a `Reveal`, not on the same element: both animate `transform`.
 */
export function ScrollDepth({ className, children }: { className?: string; children: ReactNode }) {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.15 })

  return (
    <div ref={ref} className={cn('scroll-depth', inView && 'is-flat', className)}>
      {children}
    </div>
  )
}
