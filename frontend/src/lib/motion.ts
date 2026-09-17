import { useSyncExternalStore } from 'react'

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

/**
 * Reads the reduced-motion preference right now. Safe to call from effects and event handlers; for
 * anything that changes rendered markup use `usePrefersReducedMotion`, so the prerendered landing
 * page hydrates without a mismatch.
 */
export function prefersReducedMotion() {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(REDUCED_MOTION_QUERY).matches
}

function subscribe(onChange: () => void) {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return () => {}
  const query = window.matchMedia(REDUCED_MOTION_QUERY)
  // Older Safari only has addListener.
  if (typeof query.addEventListener === 'function') {
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }
  query.addListener?.(onChange)
  return () => query.removeListener?.(onChange)
}

const serverSnapshot = () => false

/**
 * The reduced-motion preference as render state. The prerender (and hydration) render as if motion
 * is allowed; React then re-renders with the real preference straight after hydrating. The CSS
 * `prefers-reduced-motion` block already shows the final state, so that switch is not visible.
 */
export function usePrefersReducedMotion() {
  return useSyncExternalStore(subscribe, prefersReducedMotion, serverSnapshot)
}
