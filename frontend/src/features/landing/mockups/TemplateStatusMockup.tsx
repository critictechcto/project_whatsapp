import { Badge } from '../../../components/ui/Badge'
import { Window } from './Window'

const templates = [
  { name: 'order_shipped', category: 'Utility', language: 'English', status: 'approved' },
  { name: 'appointment_reminder', category: 'Utility', language: 'Hindi', status: 'approved' },
  { name: 'festive_early_access', category: 'Marketing', language: 'English', status: 'review' },
  { name: 'login_otp', category: 'Authentication', language: 'English', status: 'approved' },
  {
    name: 'payment_due',
    category: 'Utility',
    language: 'English',
    status: 'rejected',
    reason: 'Sample value missing for {{2}}',
  },
] as const

const statusBadge = {
  approved: <Badge tone="green">Approved</Badge>,
  review: <Badge tone="amber">In review</Badge>,
  rejected: <Badge tone="red">Rejected</Badge>,
}

export function TemplateStatusMockup() {
  return (
    <Window title="Templates · 5 total">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 border-b border-line-2 px-4 py-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted sm:grid-cols-[minmax(0,1.4fr)_1fr_0.8fr_auto]">
        <span>Name</span>
        <span className="hidden sm:block">Category</span>
        <span className="hidden sm:block">Language</span>
        <span>Status</span>
      </div>
      <ul>
        {templates.map((t) => (
          <li
            key={t.name}
            className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 border-b border-line-2 px-4 py-3 last:border-b-0 sm:grid-cols-[minmax(0,1.4fr)_1fr_0.8fr_auto]"
          >
            <div className="min-w-0">
              <p className="truncate font-mono text-[12px]">{t.name}</p>
              {'reason' in t && <p className="mt-0.5 text-[11px] text-signal">{t.reason}</p>}
            </div>
            <span className="hidden text-[12px] text-muted sm:block">{t.category}</span>
            <span className="hidden text-[12px] text-muted sm:block">{t.language}</span>
            {statusBadge[t.status]}
          </li>
        ))}
      </ul>
    </Window>
  )
}
