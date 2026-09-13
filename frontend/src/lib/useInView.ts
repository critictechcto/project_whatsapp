import { useEffect, useRef, useState } from 'react'
import { prefersReducedMotion } from './motion'

/**
 * Becomes true the first time the element scrolls into view, then stays true.
 * With reduced motion it starts true, so in-view animations show their final state immediately.
 */
export function useInView<T extends Element>({ rootMargin = '0px 0px -8% 0px', threshold = 0.1 } = {}) {
  const ref = useRef<T | null>(null)
  const [inView, setInView] = useState(prefersReducedMotion)

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
