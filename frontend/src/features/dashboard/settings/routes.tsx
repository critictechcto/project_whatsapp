import type { AreaRoute } from '../registry/types'

/** Routes under /app/w/:workspaceId/. Workspace settings live in `../workspaces/` but mount here. */
export const routes: AreaRoute[] = [
  {
    path: 'settings',
    handle: { title: 'Settings' },
    lazy: async () => ({ Component: (await import('./SettingsPage')).SettingsPage }),
  },
  {
    path: 'settings/profile',
    handle: { title: 'Your profile' },
    lazy: async () => ({ Component: (await import('./ProfilePage')).ProfilePage }),
  },
  {
    path: 'settings/workspace',
    handle: { title: 'Workspace settings' },
    lazy: async () => ({ Component: (await import('../workspaces/WorkspaceSettingsPage')).WorkspaceSettingsPage }),
  },
]
