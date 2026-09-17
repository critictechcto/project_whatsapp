import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { render, screen, waitFor, type ByRoleOptions, type RenderOptions } from '@testing-library/react'
import userEvent, { type UserEvent } from '@testing-library/user-event'
import type { ReactElement, ReactNode } from 'react'
import { createMemoryRouter, RouterProvider, type RouteObject } from 'react-router'
import { expect } from 'vitest'
import { createQueryClient } from '../api/queryClient'
import { ToastProvider } from '../components/app/Toast'
import { dashboardRoutes } from '../features/dashboard/router'
import { tokenStore } from '../lib/auth/tokens'
import { ids } from '../mocks/seed'
import { startMockSession } from '../mocks/session'
import { issueAccessToken } from '../mocks/utils'

/** Signs a seeded user in: an access token plus the mock refresh session the MSW handlers accept. */
export function signIn(userId: string = ids.demoUser) {
  startMockSession(userId)
  tokenStore.set(issueAccessToken(userId))
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

/**
 * Clicks a field and pastes `text` into it. For long free text whose keystrokes are not under test:
 * `user.type` dispatches four events per character and re-renders the form after each one.
 */
export async function fill(user: UserEvent, element: HTMLElement, text: string) {
  await user.click(element)
  await user.paste(text)
}

/**
 * Imports every lazy dashboard route module. The first import of a page transforms and evaluates
 * its whole chunk, which under a loaded parallel run can outlast a `findBy*` timeout; tests that
 * visit many areas in one go call this from `beforeAll` so they wait on rendering, not on imports.
 */
export async function preloadDashboardRoutes(routes: RouteObject[] = dashboardRoutes): Promise<void> {
  await Promise.all(
    routes.map(async (route) => {
      if (typeof route.lazy === 'function') await route.lazy()
      if (route.children) await preloadDashboardRoutes(route.children)
    }),
  )
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
