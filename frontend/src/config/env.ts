/// <reference types="vite/client" />

declare global {
  interface ImportMetaEnv {
    /** Absolute base path the app is served from, e.g. `/` or `/project_whatsapp/`. */
    readonly VITE_BASE?: string
    /** API origin, e.g. `http://localhost:8000`. Empty means the page's own origin. */
    readonly VITE_API_URL?: string
    /** WebSocket origin, e.g. `ws://localhost:8000`. Empty derives it from the API origin. */
    readonly VITE_WS_URL?: string
    /** `mock` serves the dashboard from MSW with seeded demo data; anything else talks to the API. */
    readonly VITE_API_MODE?: string
    /** `true` builds the dashboard alone (app.upchatz.com): no landing markup, `/` goes to `/app/`. */
    readonly VITE_APP_ONLY?: string
  }
}

function trimSlash(value: string) {
  return value.replace(/\/+$/, '')
}

function origin() {
  return typeof window === 'undefined' ? 'http://localhost' : window.location.origin
}

export const env = {
  get baseUrl(): string {
    return import.meta.env.BASE_URL
  },
  get isMock(): boolean {
    return import.meta.env.VITE_API_MODE === 'mock'
  },
  /** API origin without trailing slash. Paths from the OpenAPI schema already start with `/api/v1/`. */
  get apiUrl(): string {
    return trimSlash(import.meta.env.VITE_API_URL || origin())
  },
  get wsUrl(): string {
    const configured = import.meta.env.VITE_WS_URL
    if (configured) return trimSlash(configured)
    return this.apiUrl.replace(/^http/, 'ws')
  },
}

/** Prefixes a public asset or app path with the deploy base, e.g. `withBase('favicon.svg')`. */
export function withBase(path: string) {
  return `${import.meta.env.BASE_URL}${path.replace(/^\/+/, '')}`
}
