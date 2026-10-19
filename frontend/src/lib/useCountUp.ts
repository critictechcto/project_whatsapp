import { useEffect, useRef, useState, type RefObject } from 'react'
import { prefersReducedMotion } from './motion'

type CountUpOptions = {
  /** Animation length in ms. */
  duration?: number
  /**
   * The element showing the number. If it is already on screen when the page hydrates, the counter
   * keeps its final value instead of dropping to 0 and counting again (an `IntersectionObserver`
   * reports visibility only after the first paint, so `start` alone can't tell).
   */
  element?: RefObject<Element | null>
}

function isOnScreen(element: Element | null | undefined) {
  if (!element || typeof window === 'undefined') return false
  const rect = element.getBoundingClientRect()
  if (rect.width === 0 && rect.height === 0) return false
  return rect.top < window.innerHeight && rect.bottom > 0 && rect.left < window.innerWidth && rect.right > 0
}

/**
 * Counts up to `target` with an ease-out curve once `start` becomes true.
 *
 * The prerender and the first client render show `target` itself, so the static HTML (crawlers,
 * no-JS and slow-JS views) never reads 0 and hydration sees identical markup. After hydrating, a
 * counter that has not started and is offscreen drops to 0 so it can count up when `start` turns
 * true; nobody sees that drop. A counter already started or on screen at load, and any counter
 * under reduced motion, keeps showing `target`.
 */
export function useCountUp(target: number, start: boolean, { duration = 1400, element }: CountUpOptions = {}) {
  const [value, setValue] = useState(target)
  // 'pending' until the first effect; 'armed' counts from 0 on start; 'final' always shows target.
  const phase = useRef<'pending' | 'armed' | 'final'>('pending')

  useEffect(() => {
    if (phase.current === 'pending') {
      const animate = !start && !prefersReducedMotion() && !isOnScreen(element?.current)
      phase.current = animate ? 'armed' : 'final'
    }
    if (phase.current === 'final' || prefersReducedMotion()) {
      setValue(target)
      return
    }
    if (!start) {
      setValue(0)
      return
    }

    let frame = 0
    const startedAt = performance.now()
    const tick = (now: number) => {
      const progress = Math.min((now - startedAt) / duration, 1)
      setValue(Math.round(target * (1 - Math.pow(1 - progress, 3))))
      if (progress < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [start, target, duration, element])

  return value
}
