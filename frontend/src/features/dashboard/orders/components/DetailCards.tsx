import type { ReactNode } from 'react'
import { ExternalLink, MessageSquare, Package } from 'lucide-react'
import { Link } from 'react-router'
import { buttonClasses } from '../../../../components/app'
import { formatDateTime } from '../../../../lib/datetime'
import { formatPaise } from '../../../../lib/money'
import { useWorkspace } from '../../../../lib/workspace'
import type { Order } from '../api'
import { isBooking } from '../bookingTypes'
import { displayUrl, formatDay, formatPhone, formatWindow, itemsLabel } from '../format'
import { isCheckoutStatus, paymentMethodLabels } from '../labels'
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
  const items: { label: string; value: ReactNode }[] = [
    { label: 'Method', value: order.payment_method ? paymentMethodLabels[order.payment_method] : 'Not chosen yet' },
    { label: 'Payment', value: <PaymentBadge status={order.payment_status} method={order.payment_method} /> },
  ]
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
        {order.payment_method === 'cod'
          ? `Collect ${formatPaise(order.total_paise)} in cash when the parcel is delivered.`
          : order.payment_method === 'pay_at_shop'
            ? `The buyer pays ${formatPaise(order.total_paise)} at the shop after the service. Mark it paid here once they do.`
            : "Online payments go straight to your own payment gateway account (Razorpay or Cashfree). Refunds are made there."}
      </p>
    </SectionCard>
  )
}

/** For bookings, in place of the address and tracking cards: what the buyer asked for and the agreed time. */
export function BookingCard({ order }: { order: Order }) {
  const { timeZone } = useWorkspace()
  const items: { label: string; value: ReactNode }[] = [
    { label: 'Requested day', value: order.requested_date ? formatDay(order.requested_date) : 'Not chosen yet' },
    { label: 'Requested time', value: order.requested_window ? formatWindow(order.requested_window) : 'Not chosen yet' },
    { label: 'Appointment', value: order.appointment_at ? formatDateTime(order.appointment_at, timeZone) : 'Not confirmed yet' },
    { label: 'Payment', value: order.payment_method === 'pay_at_shop' ? 'Pay at the shop' : order.payment_method ? 'Online' : 'Not chosen yet' },
  ]
  if (order.reminder_sent_at) items.push({ label: 'Reminder sent', value: formatDateTime(order.reminder_sent_at, timeZone) })

  return (
    <SectionCard title="Booking">
      <DetailList items={items} />
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
