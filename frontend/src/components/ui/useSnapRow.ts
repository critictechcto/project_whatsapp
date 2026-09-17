import { useCallback, useEffect, useRef, useState } from 'react'
import { prefersReducedMotion } from '../../lib/motion'

/**
 * State for a horizontal CSS scroll-snap row (the row's own styles decide when it scrolls, usually
 * only on phones). Tracks which child is nearest the row's centre and scrolls a child to the centre.
 * `startAt` centres that child once on mount, only if the row actually scrolls. Reads layout only in
 * effects and handlers, so it is safe to prerender. Pair it with `SnapPager`.
 */
export function useSnapRow<T extends HTMLElement>({ startAt = 0 }: { startAt?: number } = {}) {
  const ref = useRef<T | null>(null)
  const [index, setIndex] = useState(startAt)

  const offsetFor = useCallback((row: T, i: number) => {
    const item = row.children[i] as HTMLElement | undefined
    if (!item) return null
    const rowRect = row.getBoundingClientRect()
    const itemRect = item.getBoundingClientRect()
    return row.scrollLeft + (itemRect.left - rowRect.left) - (rowRect.width - itemRect.width) / 2
  }, [])

  useEffect(() => {
    const row = ref.current
    if (!row) return

    if (startAt > 0 && row.scrollWidth > row.clientWidth + 1) {
      const left = offsetFor(row, startAt)
      if (left !== null) row.scrollLeft = left
    }

    let frame = 0
    const measure = () => {
      frame = 0
      const rowRect = row.getBoundingClientRect()
      const centre = rowRect.left + rowRect.width / 2
      let nearest = 0
      let best = Infinity
      Array.from(row.children).forEach((child, i) => {
        const rect = child.getBoundingClientRect()
        const distance = Math.abs(rect.left + rect.width / 2 - centre)
        if (distance < best) {
          best = distance
          nearest = i
        }
      })
      setIndex(nearest)
    }
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(measure)
    }
    row.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      cancelAnimationFrame(frame)
      row.removeEventListener('scroll', onScroll)
    }
  }, [startAt, offsetFor])

  const goTo = useCallback(
    (i: number) => {
      const row = ref.current
      if (!row) return
      const left = offsetFor(row, i)
      if (left === null) return
      setIndex(i)
      row.scrollTo({ left, behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
    },
    [offsetFor],
  )

  return { ref, index, goTo }
}
