import { StatusBadge } from '../../../../components/app'
import type { OrderStatus, PaymentLinkStatus, PaymentStatus } from '../api'
import { orderStatusInfo, paymentLinkStatusInfo, paymentStatusInfo } from '../labels'

export function OrderStatusBadge({ status }: { status: OrderStatus }) {
  const info = orderStatusInfo[status]
  return <StatusBadge tone={info.tone}>{info.label}</StatusBadge>
}

export function PaymentBadge({ status }: { status: PaymentStatus }) {
  const info = paymentStatusInfo[status]
  return <StatusBadge tone={info.tone}>{info.label}</StatusBadge>
}

export function PaymentLinkBadge({ status }: { status: PaymentLinkStatus }) {
  const info = paymentLinkStatusInfo[status]
  return <StatusBadge tone={info.tone}>{info.label}</StatusBadge>
}
