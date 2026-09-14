import { StatusBadge, type Tone } from '../../../../components/app'
import type { ContactImport } from '../lib/types'

const labels: Record<ContactImport['status'], { label: string; tone: Tone }> = {
  queued: { label: 'Queued', tone: 'neutral' },
  processing: { label: 'Importing', tone: 'blue' },
  completed: { label: 'Completed', tone: 'green' },
  failed: { label: 'Failed', tone: 'red' },
}

export function ImportStatusBadge({ status }: { status: ContactImport['status'] }) {
  const info = labels[status]
  return <StatusBadge tone={info.tone}>{info.label}</StatusBadge>
}
