import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { createBrowserRouter, RouterProvider } from 'react-router'
import { setActiveWorkspaceId } from '../../api/client'
import { createQueryClient } from '../../api/queryClient'
import { ToastProvider } from '../../components/app/Toast'
import '../../components/app/app.css'
import { syncLogoutAcrossTabs, tokenStore } from '../../lib/auth/tokens'
import { endSessionLocally } from './auth/session'
import { dashboardRoutes, routerBasename } from './router'
import { DemoBanner } from './shell/DemoBanner'

function useSessionLifecycle(queryClient: QueryClient) {
  useEffect(() => {
    // Another tab logged out: drop everything here too (guards then redirect to login).
    const stopSync = syncLogoutAcrossTabs(() => endSessionLocally(queryClient))
    // This tab lost its session (logout, rejected refresh): never keep tenant data around.
    const stopTokens = tokenStore.subscribe(() => {
      if (!tokenStore.hasSession()) {
        setActiveWorkspaceId(null)
        queryClient.clear()
      }
    })
    return () => {
      stopSync()
      stopTokens()
    }
  }, [queryClient])
}

/** The `/app` application. Loaded lazily by `App.tsx` (after MSW starts in mock mode). */
export default function DashboardApp() {
  const [queryClient] = useState(createQueryClient)
  const [router] = useState(() => createBrowserRouter(dashboardRoutes, { basename: routerBasename }))
  useSessionLifecycle(queryClient)

  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <DemoBanner />
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>
  )
}
