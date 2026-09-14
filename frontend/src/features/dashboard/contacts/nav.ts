import { Users } from 'lucide-react'
import type { NavItem } from '../registry/types'

/** Sidebar entries for this area. Owned by the contacts feature agent. */
export const nav: NavItem[] = [
  { id: 'contacts', label: 'Contacts', to: 'contacts', icon: Users, order: 30, group: 'main', minRole: 'viewer' },
]
