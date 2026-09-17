import type { CSSProperties, ReactNode } from 'react'
import { BatteryFull, Check, ChevronLeft, ExternalLink, List, MapPin, Mic, ShoppingCart, Signal, Wifi } from 'lucide-react'
import { usePointerTilt } from '../../../components/ui/usePointerTilt'
import { site } from '../../../config/site'
import { cn } from '../../../lib/cn'
import { SHOP_FINAL_STEP } from '../lib/useShopSequence'
import { ChatBubble } from './ChatBubble'
import { OrderTicketStack } from './OrderTicketStack'
import './ShopJourneyMockup.css'

/*
 * The "Sell on WhatsApp" journey on two phones: the buyer shopping with the seller's bot, and the
 * seller's own WhatsApp receiving the order alert, with a stack of example order tickets between
 * them. Below md only one phone shows (the seller's on the last step, otherwise the buyer's) and the
 * tickets hide. Entirely decorative; the section describes each step in text.
 */

/** Pause after a message starts popping in before its layer rises (chat-pop runs 0.45 s). */
const LIFT_AFTER_POP_MS = 450

type Beat = {
  /** Journey step at which this message appears. */
  step: number
  /** Stagger inside the step, in ms. */
  delay: number
  /**
   * While its step is showing, the message rises forward on its own layer ("card"), or only the
   * `.shop-badge` inside it does ("badge"). It settles back when the step moves on.
   */
  lift?: 'card' | 'badge'
  node: ReactNode
}

function Phone({
  name,
  subtitle,
  initials,
  avatarClassName,
  className,
  style,
  children,
}: {
  name: string
  subtitle: string
  initials: string
  avatarClassName: string
  className?: string
  style?: CSSProperties
  children: ReactNode
}) {
  return (
    <div
      style={style}
      className={cn(
        'rounded-[2.1rem] bg-ink p-[6px] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.14),inset_0_1px_0_rgb(255_255_255/0.22),0_40px_60px_-32px_rgb(16_39_31/0.5)]',
        className,
      )}
    >
      <div className="relative flex h-full flex-col overflow-hidden rounded-[1.75rem] bg-wallpaper">
        <div className="flex h-7 shrink-0 items-center justify-between bg-card px-5 font-mono text-[9px] font-medium">
          <span>11:08</span>
          <span className="absolute left-1/2 top-2 h-3.5 w-14 -translate-x-1/2 rounded-full bg-ink" />
          <span className="flex items-center gap-1">
            <Signal className="size-2.5" />
            <Wifi className="size-2.5" />
            <BatteryFull className="size-3" />
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2 border-b border-line-2 bg-card px-2 pb-2 pt-1">
          <ChevronLeft className="size-3.5 text-muted" />
          <span className={cn('grid size-7 shrink-0 place-items-center rounded-full text-[10px] font-semibold', avatarClassName)}>
            {initials}
          </span>
          <div className="min-w-0">
            <p className="truncate text-[11.5px] font-semibold leading-tight">{name}</p>
            <p className="truncate text-[9px] leading-tight text-muted">{subtitle}</p>
          </div>
        </div>
        <div className="flex min-h-0 flex-1 flex-col justify-end gap-2 overflow-hidden px-2 py-2.5">{children}</div>
        <div className="flex shrink-0 items-center gap-1.5 px-2 pb-3 pt-1">
          <div className="h-7 flex-1 rounded-full bg-white px-3 text-[10px] leading-7 text-muted">Message</div>
          <span className="grid size-7 shrink-0 place-items-center rounded-full bg-accent text-white">
            <Mic className="size-3" />
          </span>
        </div>
      </div>
    </div>
  )
}

/** An incoming business bubble with WhatsApp-style action rows. */
function Card({
  children,
  actions,
  pressed,
  time,
}: {
  children: ReactNode
  actions?: { label: string; icon?: ReactNode }[]
  /** Label of the action shown as tapped. */
  pressed?: string
  time: string
}) {
  return (
    <div className="flex justify-start">
      <div className="w-[88%] overflow-hidden rounded-lg rounded-tl-sm bg-white text-[10.5px] leading-[1.35] shadow-[0_1px_0_rgba(16,39,31,0.1)]">
        <div className="px-2.5 pt-1.5 text-ink">{children}</div>
        <p className="px-2.5 pb-1 pt-0.5 text-right text-[8.5px] text-muted">{time}</p>
        {actions && (
          <div className="divide-y divide-ink/5 border-t border-ink/5">
            {actions.map((action) => (
              <p
                key={action.label}
                className={cn(
                  'flex items-center justify-center gap-1 py-1.5 text-center font-medium text-[#1f6aa8]',
                  pressed === action.label && 'bg-[#1f6aa8]/10',
                )}
              >
                {action.icon}
                {action.label}
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/** A simple CSS drawing of a box of kaju katli for the product card. */
function ProductArt() {
  return (
    <div className="-mx-1 mb-1.5 grid h-16 place-items-center rounded-md bg-[#efe4cf]">
      <div className="grid grid-cols-3 gap-1">
        {Array.from({ length: 6 }, (_, i) => (
          <span key={i} className="size-3.5 rotate-45 rounded-[2px] border border-[#c9b58f] bg-[#f7efe0]" />
        ))}
      </div>
    </div>
  )
}

const buyerBeats: Beat[] = [
  // 0. Browse
  { step: 0, delay: 0, node: <ChatBubble from="customer" view="customer" compact time="11:02">hi</ChatBubble> },
  {
    step: 0,
    delay: 600,
    node: (
      <Card time="11:02" actions={[{ label: 'View menu', icon: <List className="size-2.5" /> }]}>
        Namaste! Welcome to Sharma Sweets. What would you like today?
      </Card>
    ),
  },
  { step: 0, delay: 1200, node: <ChatBubble from="customer" view="customer" compact time="11:03">Mithai</ChatBubble> },
  {
    step: 0,
    delay: 1800,
    lift: 'card',
    node: (
      <Card time="11:03" actions={[{ label: 'Add to cart' }, { label: 'Next item' }]} pressed="Add to cart">
        <ProductArt />
        <span className="block font-semibold">Kaju Katli 250 g</span>
        <span className="block">₹220 · made fresh every morning</span>
      </Card>
    ),
  },
  // 1. Cart
  {
    step: 1,
    delay: 0,
    lift: 'card',
    node: (
      <Card time="11:04" actions={[{ label: 'Checkout' }, { label: 'Keep shopping' }]} pressed="Checkout">
        <span className="flex items-center gap-1 font-semibold">
          <ShoppingCart className="size-3" />
          Your cart · 3 items
        </span>
        <span className="mt-1 flex justify-between gap-2">
          <span>2 × Kaju Katli 250 g</span>
          <span>₹440</span>
        </span>
        <span className="flex justify-between gap-2">
          <span>1 × Soan Papdi 250 g</span>
          <span>₹100</span>
        </span>
        <span className="mt-0.5 flex justify-between gap-2 border-t border-ink/10 pt-0.5 font-semibold">
          <span>Total</span>
          <span>₹540</span>
        </span>
      </Card>
    ),
  },
  // 2. Address
  {
    step: 2,
    delay: 0,
    node: (
      <Card time="11:04" actions={[{ label: 'Provide address', icon: <MapPin className="size-2.5" /> }]}>
        Where should we deliver your order?
      </Card>
    ),
  },
  {
    step: 2,
    delay: 700,
    node: (
      <div className="flex justify-end">
        <div className="w-[80%] rounded-lg rounded-tr-sm bg-bubble px-2.5 py-1.5 text-[10.5px] leading-[1.35] shadow-[0_1px_0_rgba(16,39,31,0.1)]">
          <span className="flex items-center gap-1 font-semibold">
            <MapPin className="size-3 text-accent-2" />
            Address shared
          </span>
          <span className="block text-muted">C-12, Malviya Nagar, Jaipur 302017</span>
        </div>
      </div>
    ),
  },
  // 3. Pay
  {
    step: 3,
    delay: 0,
    node: (
      <Card time="11:05" actions={[{ label: 'Pay online' }, { label: 'Cash on delivery' }]} pressed="Pay online">
        How would you like to pay ₹540?
      </Card>
    ),
  },
  {
    step: 3,
    delay: 800,
    node: (
      <Card time="11:05" actions={[{ label: 'Pay ₹540', icon: <ExternalLink className="size-2.5" /> }]}>
        Order SS-1042 · ₹540. Pay by UPI or card on Sharma Sweets’ payment page.
      </Card>
    ),
  },
  // 4. Order updates
  {
    step: 4,
    delay: 0,
    lift: 'badge',
    node: (
      <Card time="11:06" actions={[{ label: 'My orders' }]}>
        <span className="shop-badge mb-1 items-center gap-1 rounded-full bg-accent px-1.5 py-0.5 text-[9.5px] font-semibold text-white">
          <Check className="size-2.5" />
          Paid · ₹540
        </span>
        <span className="block">Payment received, thank you! Order SS-1042 is confirmed.</span>
      </Card>
    ),
  },
  // 5. The seller marks it shipped from the alert; the buyer hears about it.
  {
    step: 5,
    delay: 2400,
    node: (
      <Card time="16:40" actions={[{ label: 'Track order', icon: <ExternalLink className="size-2.5" /> }]}>
        Order SS-1042 has shipped with Delhivery. AWB 2841 5530 9120.
      </Card>
    ),
  },
]

const sellerBeats: Beat[] = [
  {
    step: 5,
    delay: 0,
    lift: 'card',
    node: (
      <Card time="11:06" actions={[{ label: 'Mark packed' }, { label: 'Mark shipped' }, { label: 'Cancel' }]} pressed="Mark shipped">
        <span className="block font-semibold">New order SS-1042 · ₹540</span>
        <span className="block">Paid online · Kabir, Jaipur 302017</span>
        <span className="block text-muted">2 × Kaju Katli 250 g, 1 × Soan Papdi 250 g</span>
      </Card>
    ),
  },
  {
    step: 5,
    delay: 900,
    node: <ChatBubble from="customer" view="customer" compact time="16:38">Delhivery 284155309120</ChatBubble>,
  },
  {
    step: 5,
    delay: 1700,
    node: <Card time="16:39">SS-1042 marked shipped. The buyer has been notified.</Card>,
  },
]

function Beats({ beats, step, animate }: { beats: Beat[]; step: number; animate: boolean }) {
  return beats
    .filter((beat) => step >= beat.step)
    .map((beat, i) => (
      <div
        key={`${beat.step}-${beat.delay}-${i}`}
        className={animate ? 'chat-pop' : undefined}
        style={animate ? ({ animationDelay: `${beat.delay}ms` } as CSSProperties) : undefined}
      >
        {beat.lift ? (
          // A separate element from the chat-pop wrapper, whose animation fill would pin its transform.
          <div
            className="shop-lift"
            data-lift={beat.lift}
            data-lifted={animate && step === beat.step ? '' : undefined}
            style={{ '--lift-delay': `${beat.delay + LIFT_AFTER_POP_MS}ms` } as CSSProperties}
          >
            {beat.node}
          </div>
        ) : (
          beat.node
        )}
      </div>
    ))
}

type ShopJourneyMockupProps = {
  /** Current step from `useShopSequence` (-1 before it starts). */
  step: number
  /** Pop messages in and lift layers as steps arrive; false shows everything statically (reduced motion). */
  animate: boolean
  className?: string
}

export function ShopJourneyMockup({ step, animate, className }: ShopJourneyMockupProps) {
  // Only acts on fine pointers without reduced motion; everyone else gets the resting pose.
  const tiltRef = usePointerTilt<HTMLDivElement>({ max: 5 })

  return (
    <div
      ref={tiltRef}
      aria-hidden="true"
      className={cn('shop-stage', className)}
      data-phone-focus={step >= SHOP_FINAL_STEP ? 'seller' : 'buyer'}
    >
      <div className="shop-scene shop-3d flex flex-col items-center gap-6 md:flex-row md:items-end md:justify-center">
        <Phone
          name="Sharma Sweets"
          subtitle="Business account"
          initials="SS"
          avatarClassName="bg-accent text-white"
          className="shop-depth shop-buyer-phone h-[470px] w-full max-w-[290px] md:h-[560px] md:w-[290px]"
          style={{ '--z': '24px' } as CSSProperties}
        >
          <Beats beats={buyerBeats} step={step} animate={animate} />
        </Phone>
        <div className="shop-3d shop-seller-side flex w-full max-w-[290px] flex-col gap-3 md:w-[236px]">
          <OrderTicketStack step={step} animate={animate} className="shop-depth" style={{ '--z': '64px' } as CSSProperties} />
          <div className="shop-depth flex flex-col gap-2" style={{ '--z': '-16px' } as CSSProperties}>
            <p className="text-center font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted max-md:hidden">
              Seller’s phone
            </p>
            <Phone
              name={`${site.name} Alerts`}
              subtitle="Order alerts"
              initials="UA"
              avatarClassName="bg-ink text-paper"
              className="h-[470px] w-full md:h-[410px]"
            >
              <div className={cn(step >= SHOP_FINAL_STEP && 'opacity-60')}>
                <Card time="Yesterday">SS-1039 delivered. Collect ₹860 cash on delivery from the courier.</Card>
              </div>
              <Beats beats={sellerBeats} step={step} animate={animate} />
            </Phone>
          </div>
        </div>
      </div>
    </div>
  )
}
