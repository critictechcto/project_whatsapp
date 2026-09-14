import { Smartphone } from 'lucide-react'
import type { NavItem } from '../registry/types'

/** Sidebar entries for this area. Owned by the whatsapp feature agent. */
export const nav: NavItem[] = [
  { id: 'whatsapp', label: 'WhatsApp', to: 'whatsapp', icon: Smartphone, order: 110, group: 'manage', minRole: 'viewer' },
]
