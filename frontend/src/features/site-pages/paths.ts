// Kept tiny and content-free: App.tsx imports this into the landing entry to pick the lazy chunk.

export const sitePages = ['privacy', 'terms', 'contact'] as const

export type SitePageId = (typeof sitePages)[number]

/** The static page served at `pathname` (with or without a trailing slash or `index.html`), or null. */
export function sitePageFor(pathname: string): SitePageId | null {
  const base = import.meta.env.BASE_URL
  if (!pathname.startsWith(base)) return null
  const rest = pathname
    .slice(base.length)
    .replace(/\/index\.html$/, '')
    .replace(/\/$/, '')
  return (sitePages as readonly string[]).includes(rest) ? (rest as SitePageId) : null
}
