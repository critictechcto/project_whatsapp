import { Settings } from 'lucide-react'
import type { NavItem } from '../registry/types'

/** Sidebar entries for this area. Owned by the settings feature agent. */
export const nav: NavItem[] = [
  { id: 'settings', label: 'Settings', to: 'settings', icon: Settings, order: 140, group: 'manage', minRole: 'viewer' },
]
