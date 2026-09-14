import { formatPaise } from '../../../lib/money'
import type { Role } from '../../../lib/roles'
import type { Order } from './api'

export type OrderAction = 'confirmed' | 'packed' | 'shipped' | 'delivered' | 'cod' | 'refund' | 'cancel'

/** Actions moving the order forward; the first available one is the primary button. */
export const progressActions: readonly OrderAction[] = ['confirmed', 'packed', 'shipped', 'delivered', 'cod']

/**
 * What the current member may do with the order. Status changes come only from `allowed_transitions`;
 * COD collection and refunds follow the contract's payment rules. Agents and up act; refunds need admin.
 */
export function availableOrderActions(order: Order, can: (role: Role) => boolean): OrderAction[] {
  if (!can('agent')) return []
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
  if (
    can('admin') &&
    order.payment_status === 'paid' &&
    (order.status === 'cancelled' || order.status === 'needs_attention')
  ) {
    actions.push('refund')
  }
  if (allowed.includes('cancelled')) actions.push('cancel')
  return actions
}

export const actionLabels: Record<OrderAction, string> = {
  confirmed: 'Confirm order',
  packed: 'Mark packed',
  shipped: 'Mark shipped',
  delivered: 'Mark delivered',
  cod: 'Mark COD collected',
  refund: 'Mark refunded',
  cancel: 'Cancel order',
}

export type SimpleAction = Exclude<OrderAction, 'shipped' | 'cancel'>

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
