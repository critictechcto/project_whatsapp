/** Phone helpers for the contacts UI. The server normalises again (`common.phone.normalize_e164`). */

export const E164_PATTERN = /^\+[1-9]\d{7,14}$/

/**
 * Best-effort client normalisation to E.164 so the form can validate before submitting:
 * `98765 43210` → `+919876543210`, `098765-43210` → `+919876543210`, `0091…`/`91…` → `+91…`.
 * Returns the cleaned input unchanged when it can't tell.
 */
export function normalizePhoneInput(raw: string): string {
  let value = raw.trim().replace(/[\s\-().]/g, '')
  if (!value) return ''
  if (value.startsWith('00')) value = `+${value.slice(2)}`
  if (value.startsWith('+')) return value
  if (!/^\d+$/.test(value)) return value
  if (/^[6-9]\d{9}$/.test(value)) return `+91${value}`
  if (/^0[6-9]\d{9}$/.test(value)) return `+91${value.slice(1)}`
  if (value.length > 10 && !value.startsWith('0')) return `+${value}`
  return value
}

export function isValidE164(value: string): boolean {
  return E164_PATTERN.test(value)
}

/** `+919876543210` → `+91 98765 43210`; other countries stay in E.164. */
export function formatPhone(e164: string): string {
  const match = /^\+91(\d{5})(\d{5})$/.exec(e164)
  return match ? `+91 ${match[1]} ${match[2]}` : e164
}
