import { TicketPercent } from 'lucide-react'
import type { NavItem } from '../registry/types'

/** Sidebar entry, after Store. Everyone can see offers; admins edit them and agents redeem them. */
export const nav: NavItem[] = [
  { id: 'offers', label: 'Offers', to: 'offers', icon: TicketPercent, order: 95, group: 'main', minRole: 'viewer' },
]
