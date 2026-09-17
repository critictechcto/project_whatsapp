import { useCallback, useEffect, useRef, useState } from 'react'
import { usePrefersReducedMotion } from '../../../lib/motion'

/** Browse, cart, address, pay, order updates, seller alert. */
export const SHOP_STEP_COUNT = 6
/** The whole journey visible, including the seller's alert. */
export const SHOP_FINAL_STEP = SHOP_STEP_COUNT - 1

export const SHOP_FIRST_STEP_DELAY_MS = 400
/** How long each step stays before the next one; the step progress bar fills over this time. */
export const SHOP_STEP_MS = 3000

/**
 * - `playing`: autoplay is counting down to the next step
 * - `paused`: a visitor picked a step; autoplay waits until the section leaves the screen
 * - `waiting`: offscreen, autoplay continues when it comes back
 * - `done`: the final step is showing, or reduced motion is on
 */
export type ShopAutoplay = 'playing' | 'paused' | 'waiting' | 'done'

/**
 * Drives the "Sell on WhatsApp" journey: starts at -1 (nothing shown) and plays each step once while
 * the mockup is on screen. Scrolling away pauses it; the time left on the current step is kept, so a
 * CSS progress bar paused alongside stays in sync when it continues.
 *
 * `jumpTo(step)` shows a step straight away and pauses autoplay. Leaving the screen clears that
 * pause, so autoplay resumes from the chosen step the next time the section is on screen.
 * Reduced motion starts on the final step and never autoplays; `jumpTo` still switches steps.
 */
export function useShopSequence(active: boolean) {
  // The prerender and hydration render with motion; the real preference arrives on the next render.
  const reduced = usePrefersReducedMotion()
  const [step, setStep] = useState(() => (reduced ? SHOP_FINAL_STEP : -1))
  const [wasReduced, setWasReduced] = useState(reduced)
  const [paused, setPaused] = useState(false)
  const [wasActive, setWasActive] = useState(active)
  /** Bumped by every jump, so picking the showing step again restarts its countdown. */
  const [jumps, setJumps] = useState(0)
  /** Time left on a step's countdown, carried across offscreen pauses. */
  const remaining = useRef<{ step: number; jumps: number; ms: number } | null>(null)

  // Reduced motion turning on (including right after hydration) shows the finished journey.
  if (reduced !== wasReduced) {
    setWasReduced(reduced)
    if (reduced) setStep(SHOP_FINAL_STEP)
  }

  // Leaving the screen ends a visitor's pause (state adjusted during render rather than in an effect).
  if (active !== wasActive) {
    setWasActive(active)
    if (!active) setPaused(false)
  }

  const autoplay: ShopAutoplay =
    reduced || step >= SHOP_FINAL_STEP ? 'done' : paused ? 'paused' : active ? 'playing' : 'waiting'

  useEffect(() => {
    if (autoplay !== 'playing') return
    const saved = remaining.current
    const left =
      saved && saved.step === step && saved.jumps === jumps
        ? saved.ms
        : step < 0
          ? SHOP_FIRST_STEP_DELAY_MS
          : SHOP_STEP_MS
    const started = Date.now()
    const timer = window.setTimeout(() => setStep((current) => Math.min(current + 1, SHOP_FINAL_STEP)), left)
    return () => {
      window.clearTimeout(timer)
      remaining.current = { step, jumps, ms: Math.max(0, left - (Date.now() - started)) }
    }
  }, [autoplay, step, jumps])

  const jumpTo = useCallback(
    (next: number) => {
      setStep(Math.min(Math.max(next, 0), SHOP_FINAL_STEP))
      setJumps((count) => count + 1)
      if (!reduced) setPaused(true)
    },
    [reduced],
  )

  /** Changes whenever the showing step starts a fresh countdown; key a progress bar with it. */
  const runKey = `${step}:${jumps}`

  return { step, autoplay, runKey, jumpTo }
}
