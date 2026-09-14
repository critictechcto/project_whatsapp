import { useEffect, useState } from 'react'
import { prefersReducedMotion } from '../../../lib/motion'

// The demo chat plays out once: template → customer question → agent typing → reply.
const STEP_DELAYS_MS = [500, 1400, 2300, 3700]

/** Step at which the whole conversation is visible. */
export const CHAT_FINAL_STEP = STEP_DELAYS_MS.length

/**
 * Drives the demo conversation shared by the inbox and phone mockups, so both ends of the chat
 * stay in step. Reduced motion jumps straight to the finished conversation.
 */
export function useChatSequence() {
  const [step, setStep] = useState(() => (prefersReducedMotion() ? CHAT_FINAL_STEP : 0))

  useEffect(() => {
    if (prefersReducedMotion()) {
      setStep(CHAT_FINAL_STEP)
      return
    }
    const timers = STEP_DELAYS_MS.map((delay, i) => window.setTimeout(() => setStep(i + 1), delay))
    return () => timers.forEach((timer) => window.clearTimeout(timer))
  }, [])

  return step
}
