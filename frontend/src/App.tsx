import { lazy, Suspense, useEffect } from 'react'
import { LandingPage } from './features/landing/LandingPage'
import { sitePageFor } from './features/site-pages/paths'

/*
 * The landing page and the dashboard share one entry but not one bundle: the dashboard (router,
 * react-query, UI kit, MSW in mock mode) is a separate chunk requested only for `/app` paths.
 */
const DashboardApp = lazy(async () => {
  // Before any module that may parse with zod, mock handlers included (see zodConfig.ts).
  await import('./features/dashboard/zodConfig')
  // Inline env check (not `env.isMock`) so live builds drop the MSW chunk entirely.
  if (import.meta.env.VITE_API_MODE === 'mock') {
    const { startMockWorker } = await import('./mocks/browser')
    await startMockWorker()
  }
  return import('./features/dashboard/DashboardApp')
})

// Privacy, terms and contact pages: their own chunk, so the landing bundle carries none of their text.
const SitePage = lazy(() => import('./features/site-pages/SitePage'))

function isDashboardPath(pathname: string) {
  const app = `${import.meta.env.BASE_URL}app`
  return pathname === app || pathname.startsWith(`${app}/`)
}

/**
 * App-only builds (`VITE_APP_ONLY=true`, the app.upchatz.com site) serve just the dashboard: the
 * landing and site pages live on upchatz.com, so every other path goes to the dashboard.
 */
function ToDashboard() {
  useEffect(() => {
    window.location.replace(`${import.meta.env.BASE_URL}app/`)
  }, [])
  return null
}

/**
 * Sites with `VITE_APP_URL` (upchatz.com) do not host the dashboard: `/app` links go to the same
 * path on the dashboard host.
 */
function ToAppHost({ appUrl }: { appUrl: string }) {
  useEffect(() => {
    const { pathname, search, hash } = window.location
    const path = pathname.slice(import.meta.env.BASE_URL.length)
    window.location.replace(`${appUrl.replace(/\/+$/, '')}/${path}${search}${hash}`)
  }, [appUrl])
  return null
}

export default function App() {
  // The build-time prerender has no window and renders the landing page.
  const pathname = typeof window === 'undefined' ? import.meta.env.BASE_URL : window.location.pathname
  if (isDashboardPath(pathname)) {
    const appUrl = import.meta.env.VITE_APP_URL
    if (appUrl && new URL(appUrl).origin !== window.location.origin) return <ToAppHost appUrl={appUrl} />
    return (
      <Suspense fallback={null}>
        <DashboardApp />
      </Suspense>
    )
  }
  // Inline env check with an else branch: app-only builds drop the landing and site page modules.
  if (import.meta.env.VITE_APP_ONLY === 'true') {
    return <ToDashboard />
  } else {
    const page = sitePageFor(pathname)
    if (page) {
      return (
        <Suspense fallback={null}>
          <SitePage page={page} />
        </Suspense>
      )
    }
    return <LandingPage />
  }
}
