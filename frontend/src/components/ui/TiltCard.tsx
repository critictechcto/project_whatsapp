import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'
import { usePointerTilt } from './usePointerTilt'

type TiltCardProps = {
  /** Maximum tilt in degrees. Keep it small on cards with long text. */
  max?: number
  className?: string
  children: ReactNode
}

/**
 * Card that tilts slightly towards a hovering mouse, with a soft light sheen following the pointer.
 * Touch and reduced-motion users get a static card. Styles live in index.css (.tilt-card).
 *
 * Don't put `transition-*` utilities on this element — `.tilt-card` owns the transform transition.
 * Hover transitions (border, shadow) belong on a child element.
 */
export function TiltCard({ max = 5, className, children }: TiltCardProps) {
  const ref = usePointerTilt<HTMLDivElement>({ max })

  return (
    <div ref={ref} className={cn('tilt-card', className)}>
      {children}
      <span aria-hidden="true" className="tilt-sheen" />
    </div>
  )
}
