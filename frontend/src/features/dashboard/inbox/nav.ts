import { MessagesSquare } from 'lucide-react'
import type { NavItem } from '../registry/types'

/** Sidebar entries for this area. Owned by the inbox feature agent. */
export const nav: NavItem[] = [
  { id: 'inbox', label: 'Inbox', to: 'inbox', icon: MessagesSquare, order: 20, group: 'main', minRole: 'viewer' },
]
