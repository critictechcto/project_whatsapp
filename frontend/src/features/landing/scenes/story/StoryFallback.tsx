import { useEffect, useRef, type CSSProperties, type ReactNode } from 'react'
import { BatteryFull, Check, CheckCheck, ChevronLeft, MapPin, Mic, Signal, Wifi } from 'lucide-react'
import { usePointerTilt } from '../../../../components/ui/usePointerTilt'
import { cn } from '../../../../lib/cn'
import {
  buyerChat,
  buyerMessages,
  messageStart,
  sellerChat,
  sellerEarlier,
  sellerMessages,
  storyBeats,
  beatStart,
  type StoryMessage,
} from './storyScreens'
import './storyFallback.css'

/*
 * The CSS version of the scroll story: a CSS 3D buyer phone with props that step out of it, and the
 * seller's phone in the last chapter. Everything is scrubbed by `--story-u` (chapters elapsed), which
 * `useScrollProgress` writes on the track, so scrolling never re-renders this tree. Used on phones,
 * without WebGL, and while the WebGL chunk loads. `StoryStill` is the flat, static picture of one
 * chapter for reduced motion.
 */

type Chat = typeof buyerChat

const DESIGN = { wide: [760, 640], compact: [460, 640] } as const

function vars(values: Record<string, string | number>) {
  return values as CSSProperties
}

function Phone({ chat, className, children }: { chat: Chat; className?: string; children: ReactNode }) {
  return (
    <div className={cn('sf-phone rounded-[2.1rem] bg-ink p-[6px]', className)}>
      <div className="relative flex h-full flex-col overflow-hidden rounded-[1.75rem] bg-wallpaper">
        <div className="flex h-7 shrink-0 items-center justify-between bg-card px-5 font-mono text-[9px] font-medium">
          <span>{chat.clock}</span>
          <span className="absolute left-1/2 top-2 h-3.5 w-14 -translate-x-1/2 rounded-full bg-ink" />
          <span className="flex items-center gap-1">
            <Signal className="size-2.5" />
            <Wifi className="size-2.5" />
            <BatteryFull className="size-3" />
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2 border-b border-line-2 bg-card px-2 pb-2 pt-1">
          <ChevronLeft className="size-3.5 text-muted" />
          <span
            className={cn(
              'grid size-7 shrink-0 place-items-center rounded-full text-[10px] font-semibold',
              chat === buyerChat ? 'bg-accent text-white' : 'bg-ink text-paper',
            )}
          >
            {chat.initials}
          </span>
          <div className="min-w-0">
            <p className="truncate text-[11.5px] font-semibold leading-tight">{chat.name}</p>
            <p className="truncate text-[9px] leading-tight text-muted">{chat.subtitle}</p>
          </div>
        </div>
        <div className="flex min-h-0 flex-1 flex-col justify-end overflow-hidden px-2 py-2.5">{children}</div>
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

/** A simple drawing of a box of kaju katli. */
function ProductArt({ className }: { className?: string }) {
  return (
    <div className={cn('grid place-items-center rounded-md bg-[#efe4cf]', className)}>
      <div className="grid grid-cols-3 gap-1">
        {Array.from({ length: 6 }, (_, i) => (
          <span key={i} className="size-3 rotate-45 rounded-[2px] border border-[#c9b58f] bg-[#f7efe0]" />
        ))}
      </div>
    </div>
  )
}

function Bubble({ message }: { message: StoryMessage }) {
  const out = message.side === 'out'
  const wide = Boolean(message.buttons || message.rows || message.kind === 'product')

  return (
    <div className={cn('flex', out ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[88%] overflow-hidden rounded-lg text-[10.5px] leading-[1.35] shadow-[0_1px_0_rgba(16,39,31,0.1)]',
          out ? 'rounded-tr-sm bg-bubble' : 'rounded-tl-sm bg-white',
          wide && 'w-[88%]',
        )}
      >
        <div className="px-2.5 pt-1.5 text-ink">
          {message.kind === 'product' && <ProductArt className="-mx-1 mb-1.5 h-14" />}
          {message.title && (
            <p className="flex items-center gap-1 font-semibold">
              {message.kind === 'address' && <MapPin className="size-3 text-accent-2" />}
              {message.title}
            </p>
          )}
          {message.lines?.map((line) => (
            <p key={line} className={cn(message.kind === 'address' && 'text-muted')}>
              {line}
            </p>
          ))}
          {message.rows?.map(([label, amount], i, rows) => (
            <p
              key={label}
              className={cn(
                'flex justify-between gap-2',
                i === rows.length - 1 && 'mt-0.5 border-t border-ink/10 pt-0.5 font-semibold',
              )}
            >
              <span>{label}</span>
              <span>{amount}</span>
            </p>
          ))}
        </div>
        <p className="flex items-center justify-end gap-1 px-2.5 pb-1 pt-0.5 text-[8.5px] text-muted">
          {message.time}
          {out && <CheckCheck className="size-2.5 text-[#2f7fc1]" />}
        </p>
        {message.buttons && (
          <div className="divide-y divide-ink/5 border-t border-ink/5">
            {message.buttons.map((button) => (
              <p
                key={button}
                className={cn(
                  'py-1.5 text-center font-medium text-[#1f6aa8]',
                  message.pressed === button && 'bg-[#1f6aa8]/10',
                )}
              >
                {button}
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/** Messages that grow in as `--story-u` passes each one's start. */
function ScrubbedChat({ messages }: { messages: StoryMessage[] }) {
  return messages.map((message) => (
    <div
      key={`${message.chapter}-${message.beat}`}
      className="sf-msg"
      style={vars({ '--at': messageStart(message).toFixed(3) })}
    >
      <Bubble message={message} />
    </div>
  ))
}

/** A status that lights up (or, with `fade`, fades in over what is under it) once `--story-u` passes `at`. */
function Lit({ at, fade, children, className }: { at: number; fade?: boolean; children: ReactNode; className?: string }) {
  return (
    <span className={cn(fade ? 'sf-fade' : 'sf-lit', className)} style={vars({ '--at': at.toFixed(3) })}>
      {children}
    </span>
  )
}

type PropTiming = {
  /** Position in design px (scaled by `--spread` on small stages) and depth. */
  x: number
  y: number
  z: number
  ry?: number
  /** Chapters elapsed when it starts flying out of the phone, and for how long. */
  in: [number, number]
  out?: [number, number]
  /** Where it flies to as it leaves (defaults to back into the phone). */
  to?: [number, number]
}

function Prop({ timing, className, children }: { timing: PropTiming; className?: string; children: ReactNode }) {
  const [inAt, inFor] = timing.in
  const [outAt, outFor] = timing.out ?? [99, 1]
  const [tx, ty] = timing.to ?? [-120, 0]
  return (
    <div
      className={cn('sf-prop', className)}
      style={vars({
        '--x': `${timing.x}px`,
        '--y': `${timing.y}px`,
        '--z': `${timing.z}px`,
        '--ry': `${timing.ry ?? 0}deg`,
        '--tx': `${tx}px`,
        '--ty': `${ty}px`,
        '--in-a': inAt,
        '--in-d': inFor,
        '--out-a': outAt,
        '--out-d': outFor,
      })}
    >
      {children}
    </div>
  )
}

const card = 'rounded-xl border border-line bg-card shadow-[0_24px_40px_-24px_rgb(16_39_31/0.45)]'

function TemplateCard() {
  const statuses = ['Sent', 'Delivered', 'Read']
  return (
    <div className={cn(card, 'w-[250px] p-3.5')}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[10.5px] text-ink">diwali_offer</span>
        <span className="flex items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.08em] text-accent-2">
          <Check className="size-2.5" />
          Approved
        </span>
      </div>
      <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.1em] text-muted">Marketing template</p>
      <p className="mt-2.5 text-[11.5px] leading-snug text-ink">
        Namaste {'{{1}}'}! Fresh Kaju Katli and Soan Papdi, delivered across Jaipur.
      </p>
      <div className="mt-3 flex gap-1.5">
        {statuses.map((status, beat) => (
          <Lit
            key={status}
            at={beatStart(beat, storyBeats[0]) + 0.1}
            className="rounded-full border border-line px-2 py-0.5 font-mono text-[9.5px]"
          >
            {status}
          </Lit>
        ))}
      </div>
    </div>
  )
}

const products = [
  { name: 'Kaju Katli 250 g', price: '₹220' },
  { name: 'Soan Papdi 250 g', price: '₹100' },
  { name: 'Motichoor Laddoo', price: '₹180' },
]

function ProductCard({ name, price }: { name: string; price: string }) {
  return (
    <div className={cn(card, 'w-[150px] p-2.5')}>
      <ProductArt className="h-16" />
      <p className="mt-2 text-[11.5px] font-semibold leading-tight text-ink">{name}</p>
      <p className="text-[11px] text-muted">{price}</p>
      <p className="mt-2 rounded-md border border-line py-1 text-center text-[10.5px] font-medium text-[#1f6aa8]">
        Add to cart
      </p>
    </div>
  )
}

function Parcel() {
  const shippedAt = 4 + beatStart(2, storyBeats[4])
  return (
    <div className="sf-parcel">
      <span className="sf-parcel-top" />
      <span className="sf-parcel-side" />
      <span className="sf-parcel-front">
        <span className="absolute inset-x-3 top-3 rounded-md bg-card px-2 py-1.5 text-left shadow-[0_1px_0_rgb(16_39_31/0.12)]">
          <span className="block font-mono text-[9px] text-ink">SS-1042 · Kabir</span>
          <span className="block text-[9px] text-muted">Malviya Nagar, Jaipur</span>
          <span className="relative mt-1 block font-mono text-[8.5px] uppercase tracking-[0.08em] text-amber">
            Packed
            <Lit at={shippedAt} fade className="absolute inset-0 bg-card text-accent-2">
              Shipped
            </Lit>
          </span>
        </span>
      </span>
    </div>
  )
}

function PaymentCard() {
  return (
    <div className={cn(card, 'w-[230px] p-3.5')}>
      <p className="font-mono text-[9.5px] uppercase tracking-[0.1em] text-muted">Payment link · Sharma Sweets</p>
      <p className="mt-2 font-display text-[1.7rem] font-semibold leading-none tracking-[-0.03em] text-ink">₹540</p>
      <p className="mt-1 text-[11px] text-muted">Order SS-1042 · UPI or card</p>
      <div className="relative mt-3 h-7">
        <span className="absolute inset-0 grid place-items-center rounded-md bg-ink text-[11px] font-medium text-paper">
          Pay ₹540
        </span>
        <Lit
          at={3 + beatStart(2, storyBeats[3])}
          fade
          className="absolute inset-0 flex items-center justify-center gap-1.5 rounded-md bg-accent-soft text-[11px] font-semibold text-accent-2"
        >
          <span className="grid size-4 place-items-center rounded-full bg-accent text-white">
            <Check className="size-2.5" />
          </span>
          Paid to the seller
        </Lit>
      </div>
    </div>
  )
}

/** The pinned, scroll-scrubbed CSS 3D stage. Decorative: the chapter text sits beside it. */
export function StoryFallback({ className }: { className?: string }) {
  const stageRef = useRef<HTMLDivElement>(null)
  const tiltRef = usePointerTilt<HTMLDivElement>({ max: 4, track: 'section' })

  // Scale the fixed-size design to the stage, with a narrower composition on small stages.
  useEffect(() => {
    const stage = stageRef.current
    if (!stage || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => {
      const { clientWidth: width, clientHeight: height } = stage
      const compact = width < 560
      const [designWidth, designHeight] = compact ? DESIGN.compact : DESIGN.wide
      stage.dataset.compact = String(compact)
      stage.style.setProperty('--sf-w', `${designWidth}px`)
      stage.style.setProperty('--sf-h', `${designHeight}px`)
      stage.style.setProperty('--sf-scale', Math.min(width / designWidth, height / designHeight, 1.15).toFixed(3))
    })
    observer.observe(stage)
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={stageRef} aria-hidden="true" className={cn('sf-stage', className)}>
      <div ref={tiltRef} className="sf-tilt">
        <div className="sf-scene">
          <Prop timing={{ x: 225, y: 10, z: -80, ry: -14, in: [3.85, 0.45] }}>
            <Phone chat={sellerChat} className="h-[500px] w-[250px]">
              <Bubble message={sellerEarlier} />
              <ScrubbedChat messages={sellerMessages} />
            </Phone>
          </Prop>

          <div className="sf-buyer">
            <Phone chat={buyerChat} className="h-[564px] w-[288px]">
              <ScrubbedChat messages={buyerMessages} />
            </Phone>
          </div>

          <Prop timing={{ x: -210, y: -140, z: 110, ry: 16, in: [0, 0.3], out: [0.85, 0.3] }}>
            <TemplateCard />
          </Prop>

          {products.map((product, i) => (
            <Prop
              key={product.name}
              timing={{
                x: [175, 265, 170][i],
                y: [-160, 20, 190][i],
                z: [80, 150, 100][i],
                ry: -18,
                in: [1.1 + i * 0.15, 0.35],
                out: [2.05 + i * 0.1, 0.3],
                to: [215, 170],
              }}
            >
              <ProductCard {...product} />
            </Prop>
          ))}

          <Prop timing={{ x: 215, y: 170, z: 60, ry: -24, in: [2.0, 0.35] }}>
            <Parcel />
          </Prop>

          <Prop timing={{ x: 200, y: -130, z: 130, ry: -16, in: [3.0, 0.35], out: [3.9, 0.3] }}>
            <PaymentCard />
          </Prop>

          <Prop timing={{ x: 270, y: 30, z: 180, ry: -20, in: [3.2, 0.3], out: [3.9, 0.3] }}>
            <p className={cn(card, 'flex items-center gap-2 px-3 py-2 text-[11.5px] font-medium text-ink')}>
              <span className="size-2 rounded-full bg-amber" />
              or Cash on delivery
            </p>
          </Prop>
        </div>
      </div>
    </div>
  )
}

/** One chapter as a flat, static picture, for reduced motion. Decorative. */
export function StoryStill({ chapter }: { chapter: number }) {
  const buyer = buyerMessages.filter((message) => message.chapter === chapter)
  const seller = sellerMessages.filter((message) => message.chapter === chapter)

  return (
    <div aria-hidden="true" className="flex flex-col gap-2 rounded-xl border border-line bg-wallpaper p-3">
      {seller.length > 0 && (
        <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">Seller’s WhatsApp</p>
      )}
      {seller.map((message) => (
        <Bubble key={`s-${message.beat}`} message={message} />
      ))}
      {seller.length > 0 && <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">Buyer</p>}
      {buyer.map((message) => (
        <Bubble key={`b-${message.beat}`} message={message} />
      ))}
    </div>
  )
}
