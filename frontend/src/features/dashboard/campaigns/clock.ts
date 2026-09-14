/** Current instant as an ISO string. Kept out of components so render stays pure. */
export function currentIso(): string {
  return new Date().toISOString()
}

/** Money from the API (decimal string) in the given currency, e.g. "₹10.20". */
export function formatMoney(amount: string, currency: string): string {
  const value = Number(amount)
  if (!Number.isFinite(value)) return `${currency} ${amount}`
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 2 }).format(value)
}
