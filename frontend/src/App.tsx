import { lazy, Suspense } from 'react'
import { LandingPage } from './features/landing/LandingPage'

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

function isDashboardPath(pathname: string) {
  const app = `${import.meta.env.BASE_URL}app`
  return pathname === app || pathname.startsWith(`${app}/`)
}

export default function App() {
  if (isDashboardPath(window.location.pathname)) {
    return (
      <Suspense fallback={null}>
        <DashboardApp />
      </Suspense>
    )
  }
  return <LandingPage />
}
