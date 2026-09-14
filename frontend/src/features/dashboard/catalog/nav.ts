import { Package } from 'lucide-react'
import type { NavItem } from '../registry/types'

/** Sidebar entries for this area. Owned by the catalog feature agent. */
export const nav: NavItem[] = [
  { id: 'catalog', label: 'Catalog', to: 'catalog', icon: Package, order: 70, group: 'main', minRole: 'viewer' },
]
