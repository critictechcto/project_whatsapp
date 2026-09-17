import { Navigate, type RouteObject } from 'react-router'
import { PageSpinner } from '../../components/app/Spinner'
import { RedirectIfAuthed, RequireAuth } from './auth/guards'
import { areaRoutes } from './registry'
import { AppIndexRedirect } from './shell/AppIndexRedirect'
import { NotFound, RouteError } from './shell/RouteError'

/**
 * Dashboard route tree. Paths are absolute (`/app/...`); the router basename is the deploy base.
 * Feature routes come from the registry and mount under `/app/w/:workspaceId/`.
 */
export const dashboardRoutes: RouteObject[] = [
  {
    path: '/app',
    errorElement: <RouteError />,
    hydrateFallbackElement: <PageSpinner />,
    children: [
      {
        element: <RedirectIfAuthed />,
        children: [
          { path: 'login', lazy: async () => ({ Component: (await import('./auth/LoginPage')).LoginPage }) },
          { path: 'register', lazy: async () => ({ Component: (await import('./auth/RegisterPage')).RegisterPage }) },
        ],
      },
      {
        path: 'invitations/accept',
        lazy: async () => ({ Component: (await import('./auth/AcceptInvitationPage')).AcceptInvitationPage }),
      },
      {
        element: <RequireAuth />,
        children: [
          { index: true, element: <AppIndexRedirect /> },
          {
            path: 'workspaces/new',
            lazy: async () => ({ Component: (await import('./workspaces/CreateWorkspacePage')).CreateWorkspacePage }),
          },
          {
            path: 'w/:workspaceId',
            lazy: async () => ({ Component: (await import('./shell/WorkspaceLayout')).WorkspaceLayout }),
            children: [...areaRoutes, { path: '*', element: <NotFound /> }],
          },
        ],
      },
      { path: '*', element: <NotFound /> },
    ],
  },
  { path: '*', element: <Navigate to="/app" replace /> },
]

/** Router basename from Vite's base: `/` or `/project_whatsapp`. */
export const routerBasename = import.meta.env.BASE_URL.replace(/\/+$/, '') || '/'
