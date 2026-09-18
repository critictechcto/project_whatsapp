import { areaRoutes } from '.'
import type { NavItem } from './types'

/**
 * Warms an area's code before the user opens it. React Router only fetches a lazy route's chunk
 * after the click, so without this every first visit waits for a download. Calling the route's
 * `lazy()` early starts the same dynamic import; the router's own call later resolves from cache.
 */
const started = new Set<string>()

function routesFor(to: string) {
  return areaRoutes.filter((route) => (to === '' ? route.index === true : route.path === to))
}

export function prefetchArea(to: string) {
  if (started.has(to)) return
  started.add(to)
  for (const route of routesFor(to)) {
    if (typeof route.lazy !== 'function') continue
    // A failed download is retried on the next hover (and by the router on click).
    void Promise.resolve((route.lazy as () => unknown)()).catch(() => started.delete(to))
  }
}

type IdleWindow = Window & {
  requestIdleCallback?: (callback: () => void, options?: { timeout: number }) => number
  cancelIdleCallback?: (handle: number) => void
}

type NetworkNavigator = Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }

/** False on Data Saver or 2G connections, where downloading pages nobody asked for costs the user. */
export function canPrefetchInBackground() {
  const connection = (navigator as NetworkNavigator).connection
  return !connection?.saveData && !/(^|-)2g$/.test(connection?.effectiveType ?? '')
}

/**
 * Prefetches every nav area one at a time while the browser is idle. Returns a cancel function.
 * Hover and focus prefetching still apply when this is skipped.
 */
export function prefetchAreasWhenIdle(items: readonly Pick<NavItem, 'to'>[]) {
  if (!canPrefetchInBackground()) return () => {}
  const win = window as IdleWindow
  const queue = items.map((item) => item.to)
  let handle: number | undefined
  let cancelled = false

  const schedule = (run: () => void) => {
    handle = win.requestIdleCallback ? win.requestIdleCallback(run, { timeout: 3000 }) : window.setTimeout(run, 300)
  }
  const next = () => {
    if (cancelled) return
    const to = queue.shift()
    if (to === undefined) return
    prefetchArea(to)
    schedule(next)
  }
  // Let the current page finish loading its own code and data first.
  const start = window.setTimeout(() => schedule(next), 1500)

  return () => {
    cancelled = true
    window.clearTimeout(start)
    if (handle !== undefined) {
      if (win.cancelIdleCallback) win.cancelIdleCallback(handle)
      else window.clearTimeout(handle)
    }
  }
}
