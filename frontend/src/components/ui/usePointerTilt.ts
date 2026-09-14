import { useEffect, useRef } from 'react'
import { prefersReducedMotion } from '../../lib/motion'

type PointerTiltOptions = {
  /** Maximum rotation in degrees on each axis. */
  max?: number
  /** Which element's area maps to the tilt: the element itself, or its closest <section>. */
  track?: 'self' | 'section'
}

const SETTLE_MS = 900

/** True on devices with a precise hovering pointer and no reduced-motion preference. */
export function canPointerTilt() {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(hover: hover) and (pointer: fine)').matches &&
    !prefersReducedMotion()
  )
}

/**
 * Writes pointer-driven tilt to CSS custom properties on the returned element, throttled to one
 * update per animation frame. No React state, so moving the pointer never re-renders.
 *
 * - `--tilt-x` / `--tilt-y`: rotation in degrees (the side under the pointer moves away)
 * - `--pointer-x` / `--pointer-y`: pointer position inside the element, in px
 * - `data-tilt`: "active" while the pointer is over the area, "settling" while easing back
 *
 * Touch devices and reduced-motion users get nothing, so the CSS falls back to the resting state.
 */
export function usePointerTilt<T extends HTMLElement>({ max = 6, track = 'self' }: PointerTiltOptions = {}) {
  const ref = useRef<T | null>(null)

  useEffect(() => {
    const element = ref.current
    if (!element || !canPointerTilt()) return
    const area: HTMLElement = track === 'section' ? (element.closest('section') ?? element) : element

    let frame = 0
    let settleTimer = 0
    let rect: DOMRect | null = null
    let pointer: { x: number; y: number } | null = null

    const apply = () => {
      frame = 0
      if (!pointer) return
      // Measure once per hover (and after scrolling) so the tilt itself can't feed back into the mapping.
      rect ??= area.getBoundingClientRect()
      const px = Math.min(Math.max((pointer.x - rect.left) / rect.width, 0), 1)
      const py = Math.min(Math.max((pointer.y - rect.top) / rect.height, 0), 1)
      element.style.setProperty('--tilt-x', `${((0.5 - py) * 2 * max).toFixed(2)}deg`)
      element.style.setProperty('--tilt-y', `${((px - 0.5) * 2 * max).toFixed(2)}deg`)
      element.style.setProperty('--pointer-x', `${(px * rect.width).toFixed(1)}px`)
      element.style.setProperty('--pointer-y', `${(py * rect.height).toFixed(1)}px`)
    }

    const onEnter = () => {
      window.clearTimeout(settleTimer)
      rect = null
      element.dataset.tilt = 'active'
    }
    const onMove = (event: PointerEvent) => {
      if (event.pointerType !== 'mouse' && event.pointerType !== 'pen') return
      if (element.dataset.tilt !== 'active') onEnter()
      pointer = { x: event.clientX, y: event.clientY }
      if (!frame) frame = requestAnimationFrame(apply)
    }
    const onLeave = () => {
      cancelAnimationFrame(frame)
      frame = 0
      pointer = null
      element.style.setProperty('--tilt-x', '0deg')
      element.style.setProperty('--tilt-y', '0deg')
      element.dataset.tilt = 'settling'
      settleTimer = window.setTimeout(() => {
        delete element.dataset.tilt
      }, SETTLE_MS)
    }
    const onScroll = () => {
      rect = null
    }

    area.addEventListener('pointerenter', onEnter)
    area.addEventListener('pointermove', onMove)
    area.addEventListener('pointerleave', onLeave)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      cancelAnimationFrame(frame)
      window.clearTimeout(settleTimer)
      area.removeEventListener('pointerenter', onEnter)
      area.removeEventListener('pointermove', onMove)
      area.removeEventListener('pointerleave', onLeave)
      window.removeEventListener('scroll', onScroll)
    }
  }, [max, track])

  return ref
}
