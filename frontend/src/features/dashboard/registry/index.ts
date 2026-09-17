/**
 * The one file that wires feature areas into the shell. Feature agents never edit it:
 * they edit `<area>/routes.tsx`, `<area>/nav.ts` and `<area>/mocks.ts` (mocks are wired in `./mocks.ts`).
 */
import { hasRole, type Role } from '../../../lib/roles'
import { nav as analyticsNav } from '../analytics/nav'
import { routes as analyticsRoutes } from '../analytics/routes'
import { nav as automationsNav } from '../automations/nav'
import { routes as automationsRoutes } from '../automations/routes'
import { nav as billingNav } from '../billing/nav'
import { routes as billingRoutes } from '../billing/routes'
import { nav as campaignsNav } from '../campaigns/nav'
import { routes as campaignsRoutes } from '../campaigns/routes'
import { nav as catalogNav } from '../catalog/nav'
import { routes as catalogRoutes } from '../catalog/routes'
import { nav as contactsNav } from '../contacts/nav'
import { routes as contactsRoutes } from '../contacts/routes'
import { nav as homeNav } from '../home/nav'
import { routes as homeRoutes } from '../home/routes'
import { nav as inboxNav } from '../inbox/nav'
import { routes as inboxRoutes } from '../inbox/routes'
import { nav as ordersNav } from '../orders/nav'
import { routes as ordersRoutes } from '../orders/routes'
import { nav as settingsNav } from '../settings/nav'
import { routes as settingsRoutes } from '../settings/routes'
import { nav as storeNav } from '../store/nav'
import { routes as storeRoutes } from '../store/routes'
import { nav as teamNav } from '../team/nav'
import { routes as teamRoutes } from '../team/routes'
import { nav as templatesNav } from '../templates/nav'
import { routes as templatesRoutes } from '../templates/routes'
import { nav as whatsappNav } from '../whatsapp/nav'
import { routes as whatsappRoutes } from '../whatsapp/routes'
import type { AreaRoute, NavGroup, NavItem } from './types'

export const areaRoutes: AreaRoute[] = [
  ...homeRoutes,
  ...inboxRoutes,
  ...contactsRoutes,
  ...campaignsRoutes,
  ...templatesRoutes,
  ...automationsRoutes,
  ...catalogRoutes,
  ...ordersRoutes,
  ...storeRoutes,
  ...analyticsRoutes,
  ...whatsappRoutes,
  ...teamRoutes,
  ...billingRoutes,
  ...settingsRoutes,
]

export const navItems: NavItem[] = [
  ...homeNav,
  ...inboxNav,
  ...contactsNav,
  ...campaignsNav,
  ...templatesNav,
  ...automationsNav,
  ...catalogNav,
  ...ordersNav,
  ...storeNav,
  ...analyticsNav,
  ...whatsappNav,
  ...teamNav,
  ...billingNav,
  ...settingsNav,
].sort((a, b) => a.order - b.order)

export const navGroups: { id: NavGroup; label: string }[] = [
  { id: 'main', label: 'Workspace' },
  { id: 'manage', label: 'Manage' },
]

/** Nav items visible to a role, grouped. */
export function visibleNav(role: Role | undefined) {
  return navGroups
    .map((group) => ({
      ...group,
      items: navItems.filter((item) => (item.group ?? 'main') === group.id && hasRole(role, item.minRole ?? 'viewer')),
    }))
    .filter((group) => group.items.length > 0)
}
