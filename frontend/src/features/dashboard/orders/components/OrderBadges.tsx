import { CalendarClock } from 'lucide-react'
import { StatusBadge } from '../../../../components/app'
import type { OrderKind, OrderStatus, PaymentLinkStatus, PaymentMethod, PaymentStatus } from '../api'
import { orderKindLabels, orderStatusInfo, paymentLinkStatusInfo, paymentStatusInfo } from '../labels'

export function OrderStatusBadge({ status }: { status: OrderStatus }) {
  const info = orderStatusInfo[status] ?? { label: status.replace(/_/g, ' '), tone: 'neutral' as const }
  return <StatusBadge tone={info.tone}>{info.label}</StatusBadge>
}

/** Pay-at-shop bookings reuse the COD payment statuses; they read differently there. */
const payAtShopInfo: Partial<Record<PaymentStatus, { label: string; tone: 'amber' | 'green' }>> = {
  cod_pending: { label: 'Due at shop', tone: 'amber' },
  cod_collected: { label: 'Paid at shop', tone: 'green' },
}

export function PaymentBadge({ status, method }: { status: PaymentStatus; method?: PaymentMethod | null }) {
  const info = (method === 'pay_at_shop' ? payAtShopInfo[status] : undefined) ?? paymentStatusInfo[status]
  return <StatusBadge tone={info.tone}>{info.label}</StatusBadge>
}

export function PaymentLinkBadge({ status }: { status: PaymentLinkStatus }) {
  const info = paymentLinkStatusInfo[status]
  return <StatusBadge tone={info.tone}>{info.label}</StatusBadge>
}

/** Marks bookings (services) apart from deliveries. */
export function KindBadge({ kind }: { kind: OrderKind }) {
  return (
    <span className="inline-flex h-6 items-center gap-1 whitespace-nowrap rounded-full border border-line px-2 text-[12px] font-medium text-ink-2">
      {kind === 'booking' && <CalendarClock className="size-3.5" aria-hidden="true" />}
      {orderKindLabels[kind]}
    </span>
  )
}
