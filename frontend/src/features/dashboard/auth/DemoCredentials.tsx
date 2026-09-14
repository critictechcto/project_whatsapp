import { Button } from '../../../components/app/Button'

// Mirrors src/mocks/seed.ts; kept here so the login chunk doesn't import mock data.
const DEMO_EMAIL = 'demo@upchatz.com'
const DEMO_PASSWORD = 'demo12345'

/** Shown only in mock mode: the seeded demo account. */
export function DemoCredentials({ onUse }: { onUse: (email: string, password: string) => void }) {
  if (import.meta.env.VITE_API_MODE !== 'mock') return null
  return (
    <div className="rounded-lg border border-amber/25 bg-amber-soft/60 px-3 py-2.5 text-[13px] text-ink">
      <p className="font-medium">Demo data mode</p>
      <p className="mt-0.5 text-muted">
        Use <span className="font-mono text-ink">{DEMO_EMAIL}</span> / <span className="font-mono text-ink">{DEMO_PASSWORD}</span>. Nothing is
        sent to WhatsApp.
      </p>
      <Button variant="link" size="sm" className="mt-1 h-auto px-0" onClick={() => onUse(DEMO_EMAIL, DEMO_PASSWORD)}>
        Fill in demo login
      </Button>
    </div>
  )
}
