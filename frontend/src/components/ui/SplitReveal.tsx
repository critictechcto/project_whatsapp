import type { CSSProperties, ReactNode } from 'react'
import { cn } from '../../lib/cn'
import { prefersReducedMotion } from '../../lib/motion'
import { useInView } from '../../lib/useInView'
import './SplitReveal.css'

type SplitRevealProps = {
  as?: 'h1' | 'h2' | 'h3' | 'p'
  className?: string
  /** Only a plain string is split; any other content renders as is. */
  children: ReactNode
}

/**
 * Text that rises into view a word at a time, each word behind its own mask.
 *
 * Assistive technology reads one visually hidden copy of the full string and the animated words are
 * `aria-hidden`, so the element keeps a single accessible name. Reduced motion renders plain text.
 */
export function SplitReveal({ as = 'h2', className, children }: SplitRevealProps) {
  const { ref, inView } = useInView<HTMLHeadingElement>({ threshold: 0.2 })
  // Every allowed tag accepts the same props; narrowing to one keeps the ref type simple.
  const Component = as as 'h2'

  if (typeof children !== 'string' || prefersReducedMotion()) {
    return <Component className={className}>{children}</Component>
  }

  const words = children.split(/\s+/).filter(Boolean)

  return (
    <Component ref={ref} className={cn('split-reveal', inView && 'is-visible', className)}>
      <span className="sr-only">{children}</span>
      <span aria-hidden="true">
        {words.map((word, i) => (
          <span key={i}>
            {i > 0 && ' '}
            <span className="split-reveal-word">
              <span style={{ '--word-index': i } as CSSProperties}>{word}</span>
            </span>
          </span>
        ))}
      </span>
    </Component>
  )
}
