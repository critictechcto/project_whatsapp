/**
 * Order types with the services-and-offers contract fields (`docs/contracts/services-and-offers.md`).
 *
 * TODO(api:types): the backend for bookings and offer codes is built in parallel, so `schema.d.ts` doesn't
 * have these fields yet. After `npm run api:types` the generated enums include the new values and these
 * types can become plain aliases of `Schemas[...]`.
 */
import type { Schemas } from '../../../api/types'

export type OrderKind = 'delivery' | 'booking'

export type OrderStatus = Schemas['OrderStatusEnum'] | 'awaiting_time' | 'requested' | 'completed' | 'no_show'
export type PaymentMethod = Schemas['PaymentMethodEnum'] | 'pay_at_shop'
export type EventType =
  | Schemas['OrderEventTypeEnum']
  | 'time_requested'
  | 'appointment_set'
  | 'reminder_sent'
  | 'offer_applied'
  | 'offer_removed'

/** A booking time window, `HH:MM` in the workspace time zone. */
export type BookingWindow = { label: string; start: string; end: string }

type BookingFields = {
  readonly kind: OrderKind
  /** `yyyy-MM-dd`. */
  readonly requested_date: string | null
  readonly requested_window: BookingWindow | null
  readonly appointment_at: string | null
  readonly reminder_sent_at: string | null
  readonly discount_paise: number
  /** Snapshot of the offer code text, "" when none. */
  readonly offer_code: string
  readonly offer_claim_id: string | null
}

export type Order = Omit<Schemas['Order'], 'status' | 'payment_method' | 'allowed_transitions'> &
  BookingFields & {
    readonly status: OrderStatus
    readonly payment_method: PaymentMethod | null
    readonly allowed_transitions: OrderStatus[]
  }

export type OrderListItem = Omit<Schemas['OrderListItem'], 'status' | 'payment_method'> & {
  /** Missing on servers older than the bookings contract; treat as a delivery. */
  readonly kind?: OrderKind
  readonly status: OrderStatus
  readonly payment_method: PaymentMethod | null
}

export type OrderEvent = Omit<Schemas['OrderEvent'], 'type'> & { readonly type: EventType }

export type TransitionBody = Omit<Schemas['OrderTransitionRequest'], 'to_status'> & { to_status: OrderStatus }

export type ConfirmBookingBody = { appointment_at: string }

export function isBooking(order: { kind?: OrderKind }): boolean {
  return order.kind === 'booking'
}
