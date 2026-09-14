import { useEffect, useState, type RefObject } from 'react'

/**
 * True while the element is near the viewport and the tab is visible. Unlike `useInView` it
 * turns false again, so looping animations can pause offscreen and in background tabs.
 */
export function useOnScreen<T extends Element>(ref: RefObject<T | null>, rootMargin = '80px') {
  const [onScreen, setOnScreen] = useState(false)

  useEffect(() => {
    const element = ref.current
    if (!element) return

    let intersecting = typeof IntersectionObserver === 'undefined'
    const update = () => setOnScreen(intersecting && !document.hidden)

    const observer =
      typeof IntersectionObserver === 'undefined'
        ? null
        : new IntersectionObserver(
            ([entry]) => {
              intersecting = entry.isIntersecting
              update()
            },
            { rootMargin },
          )
    observer?.observe(element)
    update()
    document.addEventListener('visibilitychange', update)

    return () => {
      observer?.disconnect()
      document.removeEventListener('visibilitychange', update)
    }
  }, [ref, rootMargin])

  return onScreen
}
