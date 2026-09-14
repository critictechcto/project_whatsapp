import { UsersRound } from 'lucide-react'
import type { NavItem } from '../registry/types'

/** Sidebar entries for this area. Owned by the team feature agent. */
export const nav: NavItem[] = [
  { id: 'team', label: 'Team', to: 'team', icon: UsersRound, order: 120, group: 'manage', minRole: 'viewer' },
]
