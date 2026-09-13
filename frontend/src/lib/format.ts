const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })

/** Formats a count with Indian digit grouping, e.g. 12480 → "12,480". */
export function formatNumber(value: number) {
  return inr.format(value)
}

/** Formats a rupee amount with Indian digit grouping, e.g. 100000 → "₹1,00,000". */
export function formatINR(amount: number) {
  return `₹${inr.format(amount)}`
}
