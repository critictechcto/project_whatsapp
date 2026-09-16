import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'

/*
 * Scroll progress through a pinned section: a tall track with a sticky stage inside it. Progress is
 * 0 when the stage first sticks and 1 when it is about to scroll away.
 *
 * Every animation frame writes the progress to CSS custom properties on the track and to a ref, and
 * notifies subscribers (the WebGL scene). React state only changes when the current chapter changes,
 * so scrolling never re-renders the section on every frame.
 */

export function clamp01(value: number) {
  return value < 0 ? 0 : value > 1 ? 1 : value
}

/**
 * Progress 0..1 of a pinned track. `trackTop` is the track's viewport top, `stageTop` the sticky
 * stage's `top` offset. A track no taller than its stage (or not laid out yet) reports 0.
 */
export function sectionProgress({
  trackTop,
  trackHeight,
  stageHeight,
  stageTop = 0,
}: {
  trackTop: number
  trackHeight: number
  stageHeight: number
  stageTop?: number
}) {
  const distance = trackHeight - stageHeight
  if (!(distance > 0)) return 0
  return clamp01((stageTop - trackTop) / distance)
}

/** Index of the chapter at `progress` when the track is split into `count` equal chapters. */
export function chapterAt(progress: number, count: number) {
  if (count <= 1) return 0
  return Math.min(count - 1, Math.max(0, Math.floor(clamp01(progress) * count)))
}

/** Progress 0..1 inside chapter `index`: 0 before it starts, 1 once it has finished. */
export function chapterLocalProgress(progress: number, count: number, index: number) {
  return clamp01(clamp01(progress) * count - index)
}

export type ScrollProgressListener = (progress: number) => void

type Options = {
  /** Number of equal chapters the track is split into. */
  count: number
  /** The sticky stage inside the track; its height and `top` define where pinning starts and ends. */
  stageRef: RefObject<HTMLElement | null>
  enabled?: boolean
}

/**
 * Tracks progress through the pinned track at `trackRef`. Writes `--story-progress` (0..1) and
 * `--story-u` (progress × count, i.e. chapters elapsed) on the track element.
 */
export function useScrollProgress<T extends HTMLElement>(
  trackRef: RefObject<T | null>,
  { count, stageRef, enabled = true }: Options,
) {
  const progressRef = useRef(0)
  const listeners = useRef(new Set<ScrollProgressListener>())
  const [chapter, setChapter] = useState(0)

  const subscribe = useCallback((listener: ScrollProgressListener) => {
    listeners.current.add(listener)
    return () => {
      listeners.current.delete(listener)
    }
  }, [])

  useEffect(() => {
    const track = trackRef.current
    if (!enabled || !track) return

    let frame = 0
    let last = -1
    let stageTop = 0
    let near = typeof IntersectionObserver === 'undefined'

    const measureStage = () => {
      const stage = stageRef.current
      stageTop = stage ? parseFloat(getComputedStyle(stage).top) || 0 : 0
    }

    const update = () => {
      frame = 0
      const rect = track.getBoundingClientRect()
      const stageHeight = stageRef.current?.offsetHeight ?? window.innerHeight
      const progress = sectionProgress({ trackTop: rect.top, trackHeight: rect.height, stageHeight, stageTop })
      if (Math.abs(progress - last) < 0.0001) return
      last = progress
      progressRef.current = progress
      track.style.setProperty('--story-progress', progress.toFixed(4))
      track.style.setProperty('--story-u', (progress * count).toFixed(4))
      listeners.current.forEach((listener) => listener(progress))
      setChapter(chapterAt(progress, count))
    }

    const schedule = () => {
      if (near && !frame) frame = requestAnimationFrame(update)
    }
    const onResize = () => {
      measureStage()
      schedule()
    }

    // Only follow scrolling while the track is near the viewport; one last update settles at 0 or 1.
    const observer =
      typeof IntersectionObserver === 'undefined'
        ? null
        : new IntersectionObserver(
            ([entry]) => {
              near = entry.isIntersecting
              if (!near) {
                cancelAnimationFrame(frame)
                update()
              } else {
                schedule()
              }
            },
            { rootMargin: '50% 0px' },
          )
    observer?.observe(track)

    measureStage()
    update()
    window.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', onResize)
    return () => {
      cancelAnimationFrame(frame)
      observer?.disconnect()
      window.removeEventListener('scroll', schedule)
      window.removeEventListener('resize', onResize)
    }
  }, [trackRef, stageRef, count, enabled])

  return { chapter, progressRef, subscribe }
}
