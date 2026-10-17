/** `+919876543210` → `+91 98765 43210`; other numbers stay as they are. */
export function formatPhone(e164: string): string {
  const match = /^\+91(\d{5})(\d{5})$/.exec(e164)
  return match ? `+91 ${match[1]} ${match[2]}` : e164
}

export function itemsLabel(count: number): string {
  return `${count} ${count === 1 ? 'item' : 'items'}`
}

/** A link without its scheme, for display: `https://rzp.io/rzp/abc` → `rzp.io/rzp/abc`. */
export function displayUrl(url: string): string {
  return url.replace(/^https?:\/\//, '').replace(/\/$/, '')
}

/** A booking window for display: `Morning (09:00–12:00)`. */
export function formatWindow(window: { label: string; start: string; end: string }): string {
  const range = `${window.start}–${window.end}`
  return window.label ? `${window.label} (${range})` : range
}

/** A `yyyy-MM-dd` day for display: `2026-10-21` → `Wed, 21 Oct 2026`. */
export function formatDay(date: string): string {
  const [year, month, day] = date.split('-').map(Number)
  if (!year || !month || !day) return date
  return new Intl.DateTimeFormat('en-IN', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(
    new Date(Date.UTC(year, month - 1, day)),
  )
}

export function isHttpsUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && Boolean(url.hostname)
  } catch {
    return false
  }
}
