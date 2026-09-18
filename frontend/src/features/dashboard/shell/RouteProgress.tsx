import { useSlowNavigation } from './useSlowNavigation'

/** Thin indeterminate bar across the top of the page while the next page loads. */
export function RouteProgress() {
  const visible = useSlowNavigation()
  if (!visible) return null
  return (
    <div
      role="progressbar"
      aria-label="Loading page"
      className="route-progress pointer-events-none fixed inset-x-0 top-0 z-[90] h-0.5 overflow-hidden bg-accent/15"
    >
      <span className="route-progress-bar block h-full w-2/5 rounded-full bg-accent" />
    </div>
  )
}
