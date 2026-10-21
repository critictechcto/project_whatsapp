import type { ReactNode } from 'react'
import { CircleCheck, ExternalLink, MessageSquare, Package } from 'lucide-react'
import { Link } from 'react-router'
import { buttonClasses } from '../../../../components/app'
import { formatDateTime } from '../../../../lib/datetime'
import { formatPaise } from '../../../../lib/money'
import { useWorkspace } from '../../../../lib/workspace'
import { isBooking, type Order } from '../api'
import { displayUrl, formatDay, formatPhone, formatWindow, itemsLabel } from '../format'
import { isCheckoutStatus, paymentMethodLabels } from '../labels'
import { Notice } from './Notice'
import { PaymentBadge, PaymentLinkBadge } from './OrderBadges'
import { DetailList, SectionCard } from './SectionCard'

const externalLinkClass = 'inline-flex items-center gap-1 break-all text-accent-2 underline-offset-4 hover:underline'

export function ItemsCard({ order }: { order: Order }) {
  const booking = isBooking(order)
  const totals: { label: string; value: string }[] = [{ label: 'Subtotal', value: formatPaise(order.subtotal_paise) }]
  if (order.discount_paise > 0) {
    totals.push({ label: order.offer_code ? `Offer ${order.offer_code}` : 'Offer', value: `−${formatPaise(order.discount_paise)}` })
  }
  if (!booking) totals.push({ label: 'Shipping', value: order.shipping_paise ? formatPaise(order.shipping_paise) : 'Free' })
  if (order.cod_fee_paise || order.payment_method === 'cod') totals.push({ label: 'COD fee', value: formatPaise(order.cod_fee_paise) })

  return (
    <SectionCard title="Items" aside={itemsLabel(order.item_count)}>
      <ul className="-mt-1 divide-y divide-line-2">
        {order.items.map((item) => (
          <li key={item.id} className="flex items-center gap-3 py-3">
            {item.image_url ? (
              <img src={item.image_url} alt="" loading="lazy" className="size-12 shrink-0 rounded-md border border-line-2 object-cover" />
            ) : (
              <div aria-hidden="true" className="grid size-12 shrink-0 place-items-center rounded-md border border-line-2 bg-paper-2 text-muted">
                <Package className="size-5" />
              </div>
            )}
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-ink">{item.name}</p>
              <p className="truncate text-[12px] text-muted">
                <span className="font-mono">{item.sku}</span> · {item.quantity} × {formatPaise(item.unit_price_paise)}
              </p>
            </div>
            <p className="shrink-0 text-sm tabular-nums text-ink">{formatPaise(item.line_total_paise)}</p>
          </li>
        ))}
      </ul>
      <dl className="mt-1 flex flex-col gap-1.5 border-t border-line-2 pt-3 text-sm">
        {totals.map((row) => (
          <div key={row.label} className="flex justify-between gap-4">
            <dt className="text-muted">{row.label}</dt>
            <dd className="tabular-nums text-ink">{row.value}</dd>
          </div>
        ))}
        <div className="mt-1 flex justify-between gap-4 border-t border-line-2 pt-2 font-medium">
          <dt className="text-ink">Total</dt>
          <dd className="font-display text-base font-semibold tabular-nums text-ink">{formatPaise(order.total_paise)}</dd>
        </div>
      </dl>
    </SectionCard>
  )
}

export function CustomerCard({ order }: { order: Order }) {
  const { workspaceId } = useWorkspace()
  const { contact } = order
  return (
    <SectionCard title="Customer">
      <p className="font-medium text-ink">{contact.name || formatPhone(contact.phone_e164)}</p>
      <a href={`tel:${contact.phone_e164}`} className="text-sm text-accent-2 underline-offset-4 hover:underline">
        {formatPhone(contact.phone_e164)}
      </a>
      <p className="mt-1 text-[13px] text-muted">
        Ordered on {order.phone_number.verified_name || 'your number'} ({order.phone_number.display_phone_number})
      </p>
      {order.conversation_id ? (
        <Link to={`/app/w/${workspaceId}/inbox/${order.conversation_id}`} className={buttonClasses('secondary', 'sm', 'mt-3')}>
          <MessageSquare className="size-4" aria-hidden="true" />
          Open conversation
        </Link>
      ) : (
        <p className="mt-3 text-[13px] text-muted">No conversation is linked to this order.</p>
      )}
    </SectionCard>
  )
}

export function AddressCard({ order }: { order: Order }) {
  const address = order.address
  return (
    <SectionCard title="Delivery address">
      {address ? (
        <address className="text-sm not-italic leading-6 text-ink">
          <span className="block font-medium">{address.name}</span>
          <span className="block">{address.line1}</span>
          {address.line2 && <span className="block">{address.line2}</span>}
          {address.landmark && <span className="block text-muted">{address.landmark}</span>}
          <span className="block">
            {address.city}, {address.state} {address.pincode}
          </span>
          <span className="block text-muted">{formatPhone(address.phone_e164)}</span>
        </address>
      ) : (
        <p className="text-sm text-muted">The buyer hasn&apos;t shared an address yet.</p>
      )}
    </SectionCard>
  )
}

export function PaymentCard({ order }: { order: Order }) {
  const { timeZone } = useWorkspace()
  const link = order.payment_link
  // A booking paid in part online (an advance): show what was paid and what is left for the shop.
  const partOnline = order.amount_paid_paise < order.total_paise && (order.advance_paise > 0 || order.amount_paid_paise > 0)
  const items: { label: string; value: ReactNode }[] = [
    {
      label: 'Method',
      value: !order.payment_method
        ? 'Not chosen yet'
        : partOnline && order.payment_method === 'online'
          ? 'Advance online, the rest at the shop'
          : paymentMethodLabels[order.payment_method],
    },
    { label: 'Payment', value: <PaymentBadge status={order.payment_status} method={order.payment_method} /> },
  ]
  if (partOnline) {
    if (order.advance_paise > 0) items.push({ label: 'Advance', value: formatPaise(order.advance_paise) })
    items.push({ label: 'Paid online', value: formatPaise(order.amount_paid_paise) })
    if (order.payment_status === 'advance_paid') {
      items.push({ label: 'Balance due', value: <span className="font-medium">{formatPaise(order.balance_due_paise)}</span> })
    } else if (order.payment_status === 'paid' && order.amount_paid_paise > 0 && order.balance_due_paise > 0) {
      items.push({ label: 'Paid at the shop', value: formatPaise(order.balance_due_paise) })
    }
  }
  if (link) {
    items.push(
      { label: 'Payment link', value: <PaymentLinkBadge status={link.status} /> },
      {
        label: 'Link',
        value: link.short_url ? (
          <a href={link.short_url} target="_blank" rel="noreferrer" className={externalLinkClass}>
            {displayUrl(link.short_url)}
            <ExternalLink className="size-3.5 shrink-0" aria-hidden="true" />
          </a>
        ) : (
          '—'
        ),
      },
      { label: 'Link amount', value: formatPaise(link.amount_paise) },
      { label: 'Link expires', value: formatDateTime(link.expires_at, timeZone) },
      { label: 'Paid', value: formatDateTime(link.paid_at, timeZone) },
    )
  }

  return (
    <SectionCard title="Payment">
      <DetailList items={items} />
      <p className="mt-3 border-t border-line-2 pt-3 text-[13px] text-muted">
        {order.payment_status === 'advance_paid'
          ? `The buyer paid a ${formatPaise(order.amount_paid_paise)} advance online. Collect the ${formatPaise(order.balance_due_paise)} balance at the shop, then mark it paid here.`
          : order.payment_method === 'cod'
          ? `Collect ${formatPaise(order.total_paise)} in cash when the parcel is delivered.`
          : order.payment_method === 'pay_at_shop'
            ? `The buyer pays ${formatPaise(order.total_paise)} at the shop after the service. Mark it paid here once they do.`
            : "Online payments go straight to your own payment gateway account (Razorpay or Cashfree). Refunds are made there."}
      </p>
    </SectionCard>
  )
}

function bookingPaymentLabel(order: Order): string {
  if (order.payment_method === 'pay_at_shop') return 'Pay at the shop'
  if (!order.payment_method) return 'Not chosen yet'
  // A booking that needs an advance, unless the buyer paid it all online.
  if (order.advance_paise > 0 && order.amount_paid_paise < order.total_paise) {
    if (order.payment_status === 'unpaid') return `Online: a ${formatPaise(order.advance_paise)} advance or in full`
    return `${formatPaise(order.advance_paise)} advance online, the rest at the shop`
  }
  return 'Online'
}

/** For bookings, in place of the address and tracking cards: what the buyer asked for and the agreed time. */
export function BookingCard({ order }: { order: Order }) {
  const { timeZone } = useWorkspace()
  const items: { label: string; value: ReactNode }[] = [
    { label: 'Requested day', value: order.requested_date ? formatDay(order.requested_date) : 'Not chosen yet' },
    { label: 'Requested time', value: order.requested_window ? formatWindow(order.requested_window) : 'Not chosen yet' },
    { label: 'Appointment', value: order.appointment_at ? formatDateTime(order.appointment_at, timeZone) : 'Not confirmed yet' },
    { label: 'Payment', value: bookingPaymentLabel(order) },
  ]
  if (order.day_before_reminder_sent_at) {
    items.push({ label: 'Reminder sent', value: `${formatDateTime(order.day_before_reminder_sent_at, timeZone)} (evening before)` })
  }
  if (order.reminder_sent_at) {
    items.push({ label: 'Reminder sent', value: `${formatDateTime(order.reminder_sent_at, timeZone)} (before the appointment)` })
  }
  const awaitingAnswer = order.status === 'confirmed'

  return (
    <SectionCard title="Booking">
      <DetailList items={items} />
      {awaitingAnswer && order.reschedule_requested_at ? (
        <Notice tone="warning" title="Customer asked to change the time" className="mt-3">
          They tapped Change time on {formatDateTime(order.reschedule_requested_at, timeZone)}. Agree a new time with them,
          then use Change time to update the booking.
        </Notice>
      ) : awaitingAnswer && order.attendance_confirmed_at ? (
        <p className="mt-3 flex items-start gap-2 border-t border-line-2 pt-3 text-[13px] text-ink-2">
          <CircleCheck className="mt-0.5 size-4 shrink-0 text-accent-2" aria-hidden="true" />
          <span>
            Customer confirmed they&apos;ll come{' '}
            <span className="text-muted">({formatDateTime(order.attendance_confirmed_at, timeZone)})</span>
          </span>
        </p>
      ) : null}
      {order.status === 'requested' && (
        <p className="mt-3 border-t border-line-2 pt-3 text-[13px] text-muted">
          Confirm a time to accept the booking. The buyer gets a WhatsApp message with it, and a reminder before the appointment.
        </p>
      )}
    </SectionCard>
  )
}

export function TrackingCard({ order }: { order: Order }) {
  const { timeZone } = useWorkspace()
  const hasTracking = Boolean(order.courier_name || order.awb_number)
  return (
    <SectionCard title="Tracking">
      {!hasTracking && order.shipped_at ? (
        <DetailList
          items={[
            { label: 'Tracking', value: 'Shipped without tracking details' },
            { label: 'Shipped', value: formatDateTime(order.shipped_at, timeZone) },
            ...(order.delivered_at ? [{ label: 'Delivered', value: formatDateTime(order.delivered_at, timeZone) }] : []),
          ]}
        />
      ) : hasTracking ? (
        <DetailList
          items={[
            { label: 'Courier', value: order.courier_name || '—' },
            { label: 'AWB', value: <span className="font-mono text-[13px]">{order.awb_number || '—'}</span> },
            {
              label: 'Tracking link',
              value: order.tracking_url ? (
                <a href={order.tracking_url} target="_blank" rel="noreferrer" className={externalLinkClass}>
                  {displayUrl(order.tracking_url)}
                  <ExternalLink className="size-3.5 shrink-0" aria-hidden="true" />
                </a>
              ) : (
                'Not added'
              ),
            },
            { label: 'Shipped', value: formatDateTime(order.shipped_at, timeZone) },
            ...(order.delivered_at ? [{ label: 'Delivered', value: formatDateTime(order.delivered_at, timeZone) }] : []),
          ]}
        />
      ) : (
        <p className="text-sm text-muted">
          {isCheckoutStatus(order.status) || order.status === 'expired'
            ? 'Tracking details are added once the order is confirmed and shipped.'
            : 'Add the courier and AWB number when you mark the order shipped, if you have them.'}
        </p>
      )}
    </SectionCard>
  )
}
