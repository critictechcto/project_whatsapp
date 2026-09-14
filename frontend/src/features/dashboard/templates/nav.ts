import { FileText } from 'lucide-react'
import type { NavItem } from '../registry/types'

/** Sidebar entries for this area. Owned by the templates feature agent. */
export const nav: NavItem[] = [
  { id: 'templates', label: 'Templates', to: 'templates', icon: FileText, order: 50, group: 'main', minRole: 'viewer' },
]
