import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { render, screen, waitFor, type ByRoleOptions, type RenderOptions } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement, ReactNode } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { expect } from 'vitest'
import { createQueryClient } from '../api/queryClient'
import { ToastProvider } from '../components/app/Toast'
import { dashboardRoutes } from '../features/dashboard/router'
import { tokenStore } from '../lib/auth/tokens'
import { ids } from '../mocks/seed'
import { issueTokens } from '../mocks/utils'

/** Signs a seeded user in (tokens accepted by the MSW handlers). */
export function signIn(userId: string = ids.demoUser) {
  tokenStore.set(issueTokens(userId))
}

export function Providers({ queryClient, children }: { queryClient: QueryClient; children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  )
}

/** Renders a component with query + toast providers and a user-event instance. */
export function renderWithProviders(ui: ReactElement, options: RenderOptions & { queryClient?: QueryClient } = {}) {
  const queryClient = options.queryClient ?? createQueryClient()
  const user = userEvent.setup()
  const result = render(ui, { ...options, wrapper: ({ children }) => <Providers queryClient={queryClient}>{children}</Providers> })
  return { ...result, queryClient, user }
}

/**
 * Finds an open dialog once its initial focus has landed. The focus manager moves focus on the next
 * animation frame; on a slow machine that frame can arrive mid-typing and send keystrokes elsewhere.
 */
export async function findDialog(options?: ByRoleOptions) {
  const dialog = await screen.findByRole('dialog', options)
  await waitFor(() => expect(dialog).toContainElement(document.activeElement as HTMLElement))
  return dialog
}

/** Renders the whole dashboard at `path` with an in-memory router. */
export function renderDashboard(path: string, { queryClient = createQueryClient() }: { queryClient?: QueryClient } = {}) {
  const router = createMemoryRouter(dashboardRoutes, { initialEntries: [path] })
  const user = userEvent.setup()
  const result = render(
    <Providers queryClient={queryClient}>
      <RouterProvider router={router} />
    </Providers>,
  )
  return { ...result, router, queryClient, user }
}
