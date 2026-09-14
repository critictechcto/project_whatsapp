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

export function isHttpsUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && Boolean(url.hostname)
  } catch {
    return false
  }
}
