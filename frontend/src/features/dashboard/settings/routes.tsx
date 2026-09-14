import { comingSoonRoute } from '../shell/comingSoon'
import type { AreaRoute } from '../registry/types'

/**
 * Routes under /app/w/:workspaceId/. Owned by the settings feature agent.
 * Replace the placeholder with lazy routes, for example:
 *
 *   { path: 'settings', handle: { title: 'Settings' }, lazy: async () => ({ Component: (await import('./SettingsPage')).SettingsPage }) }
 */
export const routes: AreaRoute[] = [
  comingSoonRoute('settings/*', 'Settings', "Workspace name, time zone and your profile."),
]
