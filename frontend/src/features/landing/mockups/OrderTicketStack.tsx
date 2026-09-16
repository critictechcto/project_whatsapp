import type { CSSProperties } from 'react'
import { Check, Clock, MapPin, ShoppingCart, Truck, type LucideIcon } from 'lucide-react'
import { cn } from '../../../lib/cn'
import './OrderTicketStack.css'

type Ticket = {
  /** Journey step at which this status arrives. */
  step: number
  status: string
  detail: string
  icon: LucideIcon
  tone: 'ink' | 'amber' | 'accent'
}

/** One example order moving through the journey; each new status lands on top of the stack. */
const tickets: Ticket[] = [
  { step: 1, status: 'Cart', detail: '3 items', icon: ShoppingCart, tone: 'ink' },
  { step: 2, status: 'Address added', detail: 'Jaipur 302017', icon: MapPin, tone: 'ink' },
  { step: 3, status: 'Awaiting payment', detail: 'Payment link sent', icon: Clock, tone: 'amber' },
  { step: 4, status: 'Paid', detail: 'Order confirmed', icon: Check, tone: 'accent' },
  { step: 5, status: 'Shipped · Delhivery', detail: 'Packed and handed over', icon: Truck, tone: 'ink' },
]

/** How many tickets show behind the newest one. */
const VISIBLE_BEHIND = 2

const toneClass: Record<Ticket['tone'], string> = {
  ink: 'bg-paper-2 text-ink',
  amber: 'bg-amber-soft text-amber',
  accent: 'bg-accent-soft text-accent-2',
}

type OrderTicketStackProps = {
  /** Current step from `useShopSequence`. */
  step: number
  /** Drop new tickets in; false shows the stack statically (reduced motion). */
  animate: boolean
  className?: string
  style?: CSSProperties
}

/**
 * A small stack of order tickets for the example order SS-1042, advancing with the "Sell on
 * WhatsApp" journey. Decorative (rendered inside the aria-hidden shop mockup, and hidden itself too);
 * depth comes from OrderTicketStack.css.
 */
export function OrderTicketStack({ step, animate, className, style }: OrderTicketStackProps) {
  const shown = tickets.filter((ticket) => step >= ticket.step)

  return (
    <div aria-hidden="true" className={cn('order-tickets', className)} style={style} data-ticket-count={shown.length}>
      <p className="text-center font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted">Example order</p>
      <div className="order-ticket-pile">
        {shown.length === 0 && (
          <div className="order-ticket grid place-items-center rounded-lg border border-dashed border-line text-[11px] text-muted">
            Waiting for an order
          </div>
        )}
        {shown.map((ticket, i) => {
          const depth = shown.length - 1 - i
          const Icon = ticket.icon
          return (
            <div
              key={ticket.step}
              className="order-ticket"
              data-depth={Math.min(depth, VISIBLE_BEHIND + 1)}
              data-ticket-status={ticket.status}
            >
              <div
                className={cn(
                  'h-full rounded-lg border border-line bg-card px-3 py-2 shadow-[0_1px_2px_rgb(16_39_31/0.06),0_14px_24px_-16px_rgb(16_39_31/0.4)]',
                  animate && depth === 0 && 'order-ticket-in',
                )}
              >
                <div className="flex items-center justify-between border-b border-dashed border-line pb-1 font-mono text-[10px] text-muted">
                  <span>SS-1042</span>
                  <span>₹540</span>
                </div>
                <div className="mt-1.5 flex items-center gap-2">
                  <span className={cn('grid size-5 shrink-0 place-items-center rounded-full', toneClass[ticket.tone])}>
                    <Icon className="size-3" />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-[12px] font-semibold leading-tight">{ticket.status}</p>
                    <p className="truncate text-[10.5px] leading-tight text-muted">{ticket.detail}</p>
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
