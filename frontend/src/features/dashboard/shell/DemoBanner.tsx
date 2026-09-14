import { FlaskConical } from 'lucide-react'

/** Visible on every dashboard page in mock mode. */
export function DemoBanner() {
  if (import.meta.env.VITE_API_MODE !== 'mock') return null
  return (
    <div className="flex items-center justify-center gap-2 border-b border-amber/20 bg-amber-soft px-4 py-1.5 text-center text-[12.5px] text-ink">
      <FlaskConical className="size-3.5 shrink-0 text-amber" aria-hidden="true" />
      <span>
        <strong className="font-medium">Demo data.</strong> Nothing is sent to WhatsApp, and changes reset when you reload.
      </span>
    </div>
  )
}
