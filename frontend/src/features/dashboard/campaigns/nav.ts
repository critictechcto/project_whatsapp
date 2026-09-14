import { Megaphone } from 'lucide-react'
import type { NavItem } from '../registry/types'

/** Sidebar entries for this area. Owned by the campaigns feature agent. */
export const nav: NavItem[] = [
  { id: 'campaigns', label: 'Campaigns', to: 'campaigns', icon: Megaphone, order: 40, group: 'main', minRole: 'viewer' },
]
