import { useEffect, useState } from 'react'
import { prefersReducedMotion } from './motion'

/** Counts from 0 to `target` with an ease-out curve once `start` becomes true. */
export function useCountUp(target: number, start: boolean, duration = 1400) {
  const [value, setValue] = useState(0)

  useEffect(() => {
    if (!start) return
    if (prefersReducedMotion()) {
      setValue(target)
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
  }, [start, target, duration])

  return value
}
