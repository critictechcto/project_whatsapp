import { FlaskConical } from 'lucide-react'
import { useLayoutEffect, useRef } from 'react'

/** CSS variable with the banner's height, so full-height layouts (inbox, sidebar) can subtract it. */
const DEMO_BANNER_HEIGHT_VAR = '--demo-banner-height'

/** Visible on every dashboard page in mock mode. */
export function DemoBanner() {
  if (import.meta.env.VITE_API_MODE !== 'mock') return null
  return <DemoBannerContent />
}

function DemoBannerContent() {
  const ref = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return
    const root = document.documentElement
    const update = () => root.style.setProperty(DEMO_BANNER_HEIGHT_VAR, `${element.offsetHeight}px`)
    update()
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update)
    observer?.observe(element)
    return () => {
      observer?.disconnect()
      root.style.removeProperty(DEMO_BANNER_HEIGHT_VAR)
    }
  }, [])

  return (
    <div
      ref={ref}
      className="flex items-center justify-center gap-2 border-b border-amber/20 bg-amber-soft px-4 py-1.5 text-center text-[12.5px] text-ink"
    >
      <FlaskConical className="size-3.5 shrink-0 text-amber" aria-hidden="true" />
      <span>
        <strong className="font-medium">Demo data.</strong> Nothing is sent to WhatsApp, and changes reset when you reload.
      </span>
    </div>
  )
}
