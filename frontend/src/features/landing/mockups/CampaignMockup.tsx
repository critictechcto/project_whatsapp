import { Check } from 'lucide-react'
import { Badge } from '../../../components/ui/Badge'
import { cn } from '../../../lib/cn'
import { formatNumber } from '../../../lib/format'
import { useCountUp } from '../../../lib/useCountUp'
import { useInView } from '../../../lib/useInView'
import { mockShadow } from './Window'

const stats = [
  { label: 'Sent', value: 12480 },
  { label: 'Delivered', value: 12103 },
  { label: 'Read', value: 9215 },
  { label: 'Replied', value: 1042 },
]

const PROGRESS = 97

function Stat({ label, value, start }: { label: string; value: number; start: boolean }) {
  const current = useCountUp(value, start)
  return (
    <div>
      <dt className="text-[10.5px] text-muted">{label}</dt>
      <dd className="mt-0.5 font-mono text-[13px] font-medium tabular-nums">{formatNumber(current)}</dd>
    </div>
  )
}

export function CampaignMockup({ className }: { className?: string }) {
  const { ref, inView } = useInView<HTMLDivElement>()
  const progress = useCountUp(PROGRESS, inView)

  return (
    <div ref={ref} aria-hidden="true" className={cn('rounded-xl border border-line bg-card p-4', mockShadow, className)}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">Campaign</p>
          <p className="mt-1 text-[14px] font-medium">Festive sale — early access</p>
        </div>
        <Badge tone="amber">Sending</Badge>
      </div>

      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted">
        <span>festive_early_access</span>
        <span>Marketing</span>
        <span>12,480 opted-in contacts</span>
      </div>

      <div className="mt-4">
        <div className="flex justify-between text-[11px]">
          <span className="text-muted">Progress</span>
          <span className="font-mono tabular-nums">{progress}%</span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-line-2">
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-[1400ms] ease-soft"
            style={{ width: inView ? `${PROGRESS}%` : '0%' }}
          />
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-4 gap-2 border-t border-line-2 pt-3">
        {stats.map((stat) => (
          <Stat key={stat.label} label={stat.label} value={stat.value} start={inView} />
        ))}
      </dl>

      <p className="mt-3 flex items-center gap-1.5 rounded-md bg-paper px-2.5 py-2 text-[11px] text-muted">
        <Check className="size-3 text-accent-2" />
        Meta charge estimate approved before sending
      </p>
    </div>
  )
}
