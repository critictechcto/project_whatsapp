import { useEffect, useRef, useState } from 'react'
import { usePrefersReducedMotion } from './motion'

/**
 * Becomes true the first time the element scrolls into view, then stays true.
 * With reduced motion it is true, so in-view animations show their final state immediately.
 */
export function useInView<T extends Element>({ rootMargin = '0px 0px -8% 0px', threshold = 0.1 } = {}) {
  const ref = useRef<T | null>(null)
  const reduced = usePrefersReducedMotion()
  const [seen, setInView] = useState(false)
  // Derived, not initial state, so the prerendered markup matches the first client render.
  const inView = seen || reduced

  useEffect(() => {
    const element = ref.current
    if (!element || inView) return
    if (typeof IntersectionObserver === 'undefined') {
      setInView(true)
      return
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true)
          observer.disconnect()
        }
      },
      { rootMargin, threshold },
    )
    observer.observe(element)
    return () => observer.disconnect()
  }, [inView, rootMargin, threshold])

  return { ref, inView }
}
