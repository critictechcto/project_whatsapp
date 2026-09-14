import { Check, CheckCheck, Clock, TriangleAlert } from 'lucide-react'
import { cn } from '../../../../lib/cn'
import type { MessageStatus } from '../api'

const labels: Record<Exclude<MessageStatus, 'received'>, string> = {
  queued: 'Sending',
  sending: 'Sending',
  sent: 'Sent',
  delivered: 'Delivered',
  read: 'Read',
  failed: 'Failed',
}

/** Delivery ticks for outbound messages: clock, ✓, ✓✓, blue ✓✓, or a warning when failed. */
export function MessageTicks({ status, className }: { status: MessageStatus; className?: string }) {
  if (status === 'received') return null
  const label = labels[status]
  const icon =
    status === 'queued' || status === 'sending' ? (
      <Clock className="size-3" aria-hidden="true" />
    ) : status === 'sent' ? (
      <Check className="size-3.5" aria-hidden="true" />
    ) : status === 'failed' ? (
      <TriangleAlert className="size-3.5 text-signal" aria-hidden="true" />
    ) : (
      <CheckCheck className={cn('size-3.5', status === 'read' && 'text-[#2f7fc1]')} aria-hidden="true" />
    )

  return (
    <span role="img" aria-label={label} title={label} className={cn('inline-flex shrink-0 items-center text-muted', className)}>
      {icon}
    </span>
  )
}
