import { ChartColumn } from 'lucide-react'
import type { NavItem } from '../registry/types'

/** Sidebar entry for this area, visible to every role. Owned by the analytics feature agent. */
export const nav: NavItem[] = [
  { id: 'analytics', label: 'Analytics', to: 'analytics', icon: ChartColumn, order: 100, group: 'main', minRole: 'viewer' },
]
