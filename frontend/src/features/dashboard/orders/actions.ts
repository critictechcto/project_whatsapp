import { formatPaise } from '../../../lib/money'
import type { Role } from '../../../lib/roles'
import { isBooking, type Order } from './api'

export type OrderAction =
  | 'confirmed'
  | 'packed'
  | 'shipped'
  | 'delivered'
  | 'cod'
  | 'confirm_time'
  | 'change_time'
  | 'completed'
  | 'no_show'
  | 'paid_at_shop'
  | 'refund'
  | 'cancel'

/** Actions moving the order forward; the first available one is the primary button. */
export const progressActions: readonly OrderAction[] = ['confirm_time', 'confirmed', 'packed', 'shipped', 'delivered', 'completed', 'cod', 'paid_at_shop']

function bookingActions(order: Order): OrderAction[] {
  const allowed = order.allowed_transitions
  const actions: OrderAction[] = []
  if (order.status === 'requested' && allowed.includes('confirmed')) actions.push('confirm_time')
  if (order.status === 'confirmed') {
    if (allowed.includes('completed')) actions.push('completed')
    if (allowed.includes('no_show')) actions.push('no_show')
    actions.push('change_time')
  }
  if (
    order.payment_method === 'pay_at_shop' &&
    order.payment_status === 'cod_pending' &&
    (order.status === 'confirmed' || order.status === 'completed')
  ) {
    actions.push('paid_at_shop')
  }
  return actions
}

function deliveryActions(order: Order): OrderAction[] {
  const allowed = order.allowed_transitions
  const actions: OrderAction[] = []
  if (order.status === 'needs_attention' && allowed.includes('confirmed')) actions.push('confirmed')
  if (allowed.includes('packed')) actions.push('packed')
  if (allowed.includes('shipped')) actions.push('shipped')
  if (allowed.includes('delivered')) actions.push('delivered')
  if (
    order.payment_method === 'cod' &&
    order.payment_status === 'cod_pending' &&
    (order.status === 'shipped' || order.status === 'delivered')
  ) {
    actions.push('cod')
  }
  return actions
}

/**
 * What the current member may do with the order. Status changes come only from `allowed_transitions`;
 * COD collection, pay at shop and refunds follow the contract's payment rules. Agents and up act; refunds need
 * admin. Bookings are never packed, shipped or delivered.
 */
export function availableOrderActions(order: Order, can: (role: Role) => boolean): OrderAction[] {
  if (!can('agent')) return []
  const actions = isBooking(order) ? bookingActions(order) : deliveryActions(order)
  if (
    can('admin') &&
    order.payment_status === 'paid' &&
    (order.status === 'cancelled' || order.status === 'needs_attention')
  ) {
    actions.push('refund')
  }
  if (order.allowed_transitions.includes('cancelled')) actions.push('cancel')
  return actions
}

export function actionLabel(action: OrderAction, order: Order): string {
  if (action === 'cancel') return isBooking(order) ? 'Cancel booking' : 'Cancel order'
  return actionLabels[action]
}

export const actionLabels: Record<OrderAction, string> = {
  confirmed: 'Confirm order',
  packed: 'Mark packed',
  shipped: 'Mark shipped',
  delivered: 'Mark delivered',
  cod: 'Mark COD collected',
  confirm_time: 'Confirm time',
  change_time: 'Change time',
  completed: 'Mark completed',
  no_show: 'Mark no-show',
  paid_at_shop: 'Mark paid at shop',
  refund: 'Mark refunded',
  cancel: 'Cancel order',
}

/** Actions with their own dialog. */
export type DialogAction = 'shipped' | 'cancel' | 'confirm_time' | 'change_time'
export type SimpleAction = Exclude<OrderAction, DialogAction>

type Copy = { title: string; description: string; confirm: string; success: string; notify: boolean }

/** Dialog copy for actions confirmed with a single click. */
export function simpleActionCopy(action: SimpleAction, order: Order): Copy {
  const copies: Record<SimpleAction, Copy> = {
    confirmed: {
      title: `Confirm ${order.number}?`,
      description:
        'Only confirm if you can still fulfil it. The buyer has paid, and the order moves on to packing like any other confirmed order.',
      confirm: 'Confirm order',
      success: 'Order confirmed',
      notify: true,
    },
    packed: {
      title: `Mark ${order.number} packed?`,
      description: 'Use this once the parcel is ready for the courier.',
      confirm: 'Mark packed',
      success: 'Marked packed',
      notify: true,
    },
    delivered: {
      title: `Mark ${order.number} delivered?`,
      description: 'Use this once the courier has handed the parcel to the buyer. Delivered orders are closed.',
      confirm: 'Mark delivered',
      success: 'Marked delivered',
      notify: true,
    },
    cod: {
      title: 'Mark cash collected?',
      description: `Records that ${formatPaise(order.total_paise)} was collected in cash on delivery.`,
      confirm: 'Mark collected',
      success: 'Cash on delivery collected',
      notify: false,
    },
    completed: {
      title: `Mark ${order.number} completed?`,
      description: 'Use this once the service is done. Completed bookings are closed.',
      confirm: 'Mark completed',
      success: 'Marked completed',
      notify: false,
    },
    no_show: {
      title: `Mark ${order.number} as a no-show?`,
      description: "Use this when the buyer didn't come for the appointment. The booking is closed.",
      confirm: 'Mark no-show',
      success: 'Marked no-show',
      notify: false,
    },
    paid_at_shop: {
      title: 'Mark paid at the shop?',
      description: `Records that the buyer paid ${formatPaise(order.total_paise)} at the shop.`,
      confirm: 'Mark paid',
      success: 'Marked paid at the shop',
      notify: false,
    },
    refund: {
      title: 'Mark as refunded?',
      description:
        "Refund the buyer in your payment gateway (Razorpay or Cashfree) first. This only records the refund here: UpChatz doesn't hold or move the buyer's money.",
      confirm: 'Mark refunded',
      success: 'Marked refunded',
      notify: false,
    },
  }
  return copies[action]
}
