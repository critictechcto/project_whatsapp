import { Workflow } from 'lucide-react'
import type { NavItem } from '../registry/types'

/** Sidebar entries for this area. Owned by the automations feature agent. */
export const nav: NavItem[] = [
  { id: 'automations', label: 'Automations', to: 'automations', icon: Workflow, order: 60, group: 'main', minRole: 'viewer' },
]
