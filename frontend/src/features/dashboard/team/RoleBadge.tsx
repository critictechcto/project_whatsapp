import { StatusBadge } from '../../../components/app'
import { roleLabels, type Role } from '../../../lib/roles'
import { roleTones } from './roles'

export function RoleBadge({ role }: { role: Role }) {
  return <StatusBadge tone={roleTones[role]}>{roleLabels[role]}</StatusBadge>
}
