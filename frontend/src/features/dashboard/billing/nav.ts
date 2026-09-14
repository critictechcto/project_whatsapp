import { CreditCard } from 'lucide-react'
import type { NavItem } from '../registry/types'

/** Sidebar entries for this area. Owned by the billing feature agent. */
export const nav: NavItem[] = [
  { id: 'billing', label: 'Billing', to: 'billing', icon: CreditCard, order: 130, group: 'manage', minRole: 'admin' },
]
