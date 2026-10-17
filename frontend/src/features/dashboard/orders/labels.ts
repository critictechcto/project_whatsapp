import { errorMessage, isApiError } from '../../../api/errors'
import type { Tone } from '../../../components/app'
import type {
  EventActor,
  EventType,
  OrderEvent,
  OrderKind,
  OrderSource,
  OrderStatus,
  PaymentLinkStatus,
  PaymentMethod,
  PaymentStatus,
} from './api'

type Info = { label: string; tone: Tone }

export const orderStatusInfo: Record<OrderStatus, Info> = {
  draft: { label: 'Cart started', tone: 'neutral' },
  awaiting_confirmation: { label: 'Confirming prices', tone: 'amber' },
  awaiting_address: { label: 'Awaiting address', tone: 'amber' },
  awaiting_time: { label: 'Choosing a time', tone: 'amber' },
  awaiting_payment_method: { label: 'Choosing payment', tone: 'amber' },
  pending_payment: { label: 'Awaiting payment', tone: 'amber' },
  requested: { label: 'Booking requested', tone: 'amber' },
  confirmed: { label: 'Confirmed', tone: 'blue' },
  packed: { label: 'Packed', tone: 'blue' },
  shipped: { label: 'Shipped', tone: 'blue' },
  delivered: { label: 'Delivered', tone: 'green' },
  completed: { label: 'Completed', tone: 'green' },
  no_show: { label: 'No-show', tone: 'neutral' },
  cancelled: { label: 'Cancelled', tone: 'neutral' },
  expired: { label: 'Expired', tone: 'neutral' },
  needs_attention: { label: 'Needs attention', tone: 'red' },
}

export const paymentStatusInfo: Record<PaymentStatus, Info> = {
  paid: { label: 'Paid', tone: 'green' },
  cod_pending: { label: 'COD pending', tone: 'amber' },
  cod_collected: { label: 'COD collected', tone: 'green' },
  unpaid: { label: 'Unpaid', tone: 'neutral' },
  refunded_manual: { label: 'Refunded', tone: 'neutral' },
}

export const paymentMethodLabels: Record<PaymentMethod, string> = {
  online: 'Paid online',
  cod: 'Cash on delivery',
  pay_at_shop: 'Pay at the shop',
}

export const orderKindLabels: Record<OrderKind, string> = {
  delivery: 'Delivery',
  booking: 'Booking',
}

export const sourceLabels: Record<OrderSource, string> = {
  bot: 'Bot',
  native_cart: 'WhatsApp cart',
}

export const paymentLinkStatusInfo: Record<PaymentLinkStatus, Info> = {
  creating: { label: 'Creating', tone: 'neutral' },
  created: { label: 'Waiting for payment', tone: 'amber' },
  paid: { label: 'Paid', tone: 'green' },
  expired: { label: 'Expired', tone: 'neutral' },
  cancelled: { label: 'Cancelled', tone: 'neutral' },
  failed: { label: 'Failed', tone: 'red' },
}

/** Stage filter of `GET orders/`, as in the contract. */
export const stageStatuses = {
  checkout: ['draft', 'awaiting_confirmation', 'awaiting_address', 'awaiting_time', 'awaiting_payment_method', 'pending_payment'],
  open: ['requested', 'confirmed', 'packed', 'shipped', 'needs_attention'],
  closed: ['delivered', 'completed', 'no_show', 'cancelled', 'expired'],
} as const satisfies Record<string, readonly OrderStatus[]>

export function isCheckoutStatus(status: OrderStatus): boolean {
  return (stageStatuses.checkout as readonly OrderStatus[]).includes(status)
}

/** The contract's transitions table for deliveries: every status a seller may move an order to. */
export const orderTransitions: Record<OrderStatus, readonly OrderStatus[]> = {
  draft: ['cancelled'],
  awaiting_confirmation: ['cancelled'],
  awaiting_address: ['cancelled'],
  awaiting_time: ['cancelled'],
  awaiting_payment_method: ['cancelled'],
  pending_payment: ['cancelled'],
  requested: [],
  confirmed: ['packed', 'shipped', 'cancelled'],
  packed: ['shipped', 'cancelled'],
  shipped: ['delivered'],
  needs_attention: ['confirmed', 'cancelled'],
  delivered: [],
  completed: [],
  no_show: [],
  cancelled: [],
  expired: [],
}

/**
 * Bookings: `requested → confirmed | cancelled` and `confirmed → completed | no_show | cancelled`; they are
 * never packed, shipped or delivered. `confirmed` from `requested` goes through `confirm-booking`.
 */
export const bookingTransitions: Record<OrderStatus, readonly OrderStatus[]> = {
  ...orderTransitions,
  requested: ['confirmed', 'cancelled'],
  confirmed: ['completed', 'no_show', 'cancelled'],
  packed: [],
  shipped: [],
  needs_attention: ['requested', 'cancelled'],
}

export function transitionsFor(kind: OrderKind | undefined, status: OrderStatus): readonly OrderStatus[] {
  return (kind === 'booking' ? bookingTransitions : orderTransitions)[status]
}

export const eventTypeLabels: Record<EventType, string> = {
  created: 'Order started',
  status_changed: 'Status changed',
  price_changed: 'Prices changed at checkout',
  address_received: 'Delivery address received',
  time_requested: 'Booking day and time chosen',
  appointment_set: 'Appointment time set',
  reminder_sent: 'Appointment reminder sent',
  offer_applied: 'Offer applied',
  offer_removed: 'Offer removed',
  payment_link_created: 'Payment link sent',
  payment_received: 'Payment received',
  payment_link_expired: 'Payment link expired',
  cod_collected: 'Cash on delivery collected',
  refunded_manual: 'Marked refunded',
  stock_released: 'Items returned to stock',
  notification_sent: 'Buyer notified',
  notification_failed: 'Buyer notification not sent',
  note: 'Note',
}

function statusLabel(status: string): string {
  return orderStatusInfo[status as OrderStatus]?.label ?? status.replace(/_/g, ' ')
}

/** Title of a timeline entry. */
export function eventTitle(event: Pick<OrderEvent, 'type' | 'to_status'>): string {
  if (event.type === 'status_changed' && event.to_status) return `Moved to ${statusLabel(event.to_status)}`
  return eventTypeLabels[event.type] ?? event.type
}

/** Who did it: the buyer, a dashboard user, the seller from WhatsApp alerts or the system. */
export function eventActor(event: Pick<OrderEvent, 'actor' | 'user'>, buyerName: string): string {
  const userName = event.user ? event.user.full_name || event.user.email : ''
  const labels: Record<EventActor, string> = {
    buyer: buyerName ? `${buyerName} (buyer)` : 'Buyer',
    dashboard: userName || 'A team member',
    seller_whatsapp: userName ? `${userName} via WhatsApp alerts` : 'Seller via WhatsApp alerts',
    system: 'Automatic',
  }
  return labels[event.actor] ?? event.actor
}

function joinOr(items: string[]): string {
  if (items.length <= 1) return items.join('')
  return `${items.slice(0, -1).join(', ')} or ${items.at(-1)}`
}

type TransitionDetails = { from_status?: string; to_status?: string; allowed?: string[] }

/** A readable message for a failed order action, with `invalid_order_transition` details spelled out. */
export function orderActionError(error: unknown): string {
  if (!isApiError(error, 'invalid_order_transition') && !isApiError(error, 'invalid_transition')) return errorMessage(error)
  const details = (error.details ?? {}) as TransitionDetails
  const from = details.from_status ? statusLabel(details.from_status) : ''
  const to = details.to_status ? statusLabel(details.to_status) : ''
  const allowed = (details.allowed ?? []).map((status) => statusLabel(status).toLowerCase())
  const next = allowed.length ? `From here it can only be moved to ${joinOr(allowed)}.` : "Its status can't be changed any more."
  if (!from || !to || from === to) return `${error.message} ${next}`.trim()
  return `This order is ${from.toLowerCase()} now, so it can't be moved to ${to.toLowerCase()}. ${next}`
}
