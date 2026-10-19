import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useCountUp } from './useCountUp'

const motion = vi.hoisted(() => ({ reduced: false }))

vi.mock('./motion', () => ({ prefersReducedMotion: () => motion.reduced }))

function elementAt(top: number) {
  const element = document.createElement('div')
  element.getBoundingClientRect = () =>
    ({ top, bottom: top + 100, left: 0, right: 300, width: 300, height: 100, x: 0, y: top }) as DOMRect
  return { current: element }
}

/** Renders the hook and records every value it returned, starting with the first render. */
function renderCounter(target: number, start: boolean, element?: { current: Element | null }) {
  const seen: number[] = []
  const view = renderHook(
    ({ start }) => {
      const value = useCountUp(target, start, { duration: 1000, element })
      seen.push(value)
      return value
    },
    { initialProps: { start } },
  )
  return { ...view, seen }
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['requestAnimationFrame', 'cancelAnimationFrame', 'performance'] })
})

afterEach(() => {
  vi.useRealTimers()
  motion.reduced = false
})

describe('useCountUp', () => {
  it('renders the final value first, then drops to 0 while waiting offscreen', () => {
    const { result, seen } = renderCounter(97, false, elementAt(2000))
    expect(seen[0]).toBe(97)
    expect(result.current).toBe(0)
  })

  it('counts up to the target once started', () => {
    const { result, rerender } = renderCounter(97, false, elementAt(2000))
    rerender({ start: true })

    act(() => vi.advanceTimersByTime(500))
    expect(result.current).toBeGreaterThan(0)
    expect(result.current).toBeLessThan(97)

    act(() => vi.advanceTimersByTime(600))
    expect(result.current).toBe(97)
  })

  it('keeps the target under reduced motion', () => {
    motion.reduced = true
    const { result, rerender, seen } = renderCounter(97, false, elementAt(2000))
    rerender({ start: true })
    act(() => vi.advanceTimersByTime(1100))

    expect(seen.every((value) => value === 97)).toBe(true)
    expect(result.current).toBe(97)
  })

  it('keeps the target when already started at hydration', () => {
    const { result, seen } = renderCounter(97, true)
    act(() => vi.advanceTimersByTime(1100))
    expect(seen.every((value) => value === 97)).toBe(true)
    expect(result.current).toBe(97)
  })

  it('keeps the target when the element is on screen at hydration', () => {
    const { result, rerender, seen } = renderCounter(97, false, elementAt(100))
    rerender({ start: true })
    act(() => vi.advanceTimersByTime(1100))
    expect(seen.every((value) => value === 97)).toBe(true)
    expect(result.current).toBe(97)
  })
})
