import { Store } from 'lucide-react'
import type { NavItem } from '../registry/types'

/** Sidebar entries for this area. Owned by the store feature agent. Store setup is for admins and owners. */
export const nav: NavItem[] = [
  { id: 'store', label: 'Store', to: 'store', icon: Store, order: 90, group: 'main', minRole: 'admin' },
]
