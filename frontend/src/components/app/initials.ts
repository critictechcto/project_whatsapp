/** "Priya Nair" -> "PN", "rohan@x.com" -> "RX". */
export function initials(name: string) {
  const parts = name.trim().split(/[\s@._-]+/).filter(Boolean)
  if (!parts.length) return '?'
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase()
}
