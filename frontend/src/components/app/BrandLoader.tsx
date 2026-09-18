import type { CSSProperties } from 'react'
import { site } from '../../config/site'
import { cn } from '../../lib/cn'

type BrandLoaderProps = {
  /** Accessible label announced while loading. */
  label?: string
  className?: string
}

/**
 * The UpChatz wordmark as a loader: a wave runs through the letters, lifting each one and tinting it
 * accent green in turn. Styles live in `index.css` (`.brand-loader`); reduced motion shows the still
 * word. It fades in after a short delay so quick loads never flash it.
 */
export function BrandLoader({ label = 'Loading', className }: BrandLoaderProps) {
  return (
    <div role="status" aria-label={label} className={cn('brand-loader', className)}>
      <span aria-hidden="true" className="font-display text-2xl font-semibold tracking-[-0.03em] text-ink">
        {Array.from(site.name).map((letter, index) => (
          <span key={index} className="brand-loader-letter" style={{ '--i': index } as CSSProperties}>
            {letter}
          </span>
        ))}
      </span>
    </div>
  )
}
