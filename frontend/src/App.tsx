import { lazy, Suspense } from 'react'
import { LandingPage } from './features/landing/LandingPage'
import { sitePageFor } from './features/site-pages/paths'

/*
 * The landing page and the dashboard share one entry but not one bundle: the dashboard (router,
 * react-query, UI kit, MSW in mock mode) is a separate chunk requested only for `/app` paths.
 */
const DashboardApp = lazy(async () => {
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

export default function App() {
  // The build-time prerender has no window and renders the landing page.
  const pathname = typeof window === 'undefined' ? import.meta.env.BASE_URL : window.location.pathname
  if (isDashboardPath(pathname)) {
    return (
      <Suspense fallback={null}>
        <DashboardApp />
      </Suspense>
    )
  }
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
