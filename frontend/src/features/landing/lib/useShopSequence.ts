import { useEffect, useState } from 'react'
import { prefersReducedMotion } from '../../../lib/motion'

/** Browse, cart, address, pay, order updates, seller alert. */
export const SHOP_STEP_COUNT = 6
/** The whole journey visible, including the seller's alert. */
export const SHOP_FINAL_STEP = SHOP_STEP_COUNT - 1

const FIRST_STEP_DELAY_MS = 400
const STEP_MS = 3000

/**
 * Drives the "Sell on WhatsApp" journey: starts at -1 (nothing shown) and plays each step once while
 * the mockup is on screen, pausing when it scrolls away. Reduced motion jumps to the final step.
 */
export function useShopSequence(active: boolean) {
  const [step, setStep] = useState(() => (prefersReducedMotion() ? SHOP_FINAL_STEP : -1))

  useEffect(() => {
    if (prefersReducedMotion()) {
      setStep(SHOP_FINAL_STEP)
      return
    }
    if (!active || step >= SHOP_FINAL_STEP) return
    const timer = window.setTimeout(() => setStep((current) => Math.min(current + 1, SHOP_FINAL_STEP)), step < 0 ? FIRST_STEP_DELAY_MS : STEP_MS)
    return () => window.clearTimeout(timer)
  }, [active, step])

  return step
}
