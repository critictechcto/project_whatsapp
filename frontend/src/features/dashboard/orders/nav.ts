import { ShoppingBag } from 'lucide-react'
import type { NavItem } from '../registry/types'

/** Sidebar entries for this area. Owned by the orders feature agent. */
export const nav: NavItem[] = [
  { id: 'orders', label: 'Orders', to: 'orders', icon: ShoppingBag, order: 80, group: 'main', minRole: 'viewer' },
]
