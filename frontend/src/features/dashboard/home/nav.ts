import { House } from 'lucide-react'
import type { NavItem } from '../registry/types'

/** Sidebar entries for this area. */
export const nav: NavItem[] = [{ id: 'home', label: 'Home', to: '', icon: House, order: 10, group: 'main', end: true }]
