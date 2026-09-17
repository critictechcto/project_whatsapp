import { useRef, type CSSProperties } from 'react'
import { Container } from '../../../components/ui/Container'
import { Reveal } from '../../../components/ui/Reveal'
import { SectionHeader } from '../../../components/ui/SectionHeader'
import { site } from '../../../config/site'
import { cn } from '../../../lib/cn'
import { usePrefersReducedMotion } from '../../../lib/motion'
import { useOnScreen } from '../lib/useOnScreen'
import { SHOP_STEP_MS, useShopSequence, type ShopAutoplay } from '../lib/useShopSequence'
import { ShopJourneyMockup } from '../mockups/ShopJourneyMockup'
import './SellOnWhatsApp.css'
import { SwipeRow } from './SwipeRow'

const steps = [
  {
    title: 'Browse the menu',
    body: 'A buyer sends “hi” to your number and gets your menu. They open a collection and see product cards with prices.',
  },
  {
    title: 'Build a cart',
    body: 'Items go into the cart with a tap. If you connect a Meta catalog, buyers can also shop with WhatsApp’s own cart.',
  },
  {
    title: 'Share an address',
    body: 'Buyers send their delivery address through WhatsApp’s address form, or simply type it.',
  },
  {
    title: 'Pay by link or cash on delivery',
    body: 'Online payments use a UPI or card payment link from your own Razorpay or Cashfree account. Buyers can also choose cash on delivery if you offer it.',
  },
  {
    title: 'Get order updates',
    body: 'Buyers hear when their order is confirmed, packed, shipped and delivered, and can check “My orders” at any time.',
  },
  {
    title: 'Manage orders from your phone',
    body: `New orders reach your personal WhatsApp from the ${site.name} alerts number. Tap Mark packed, Mark shipped or Cancel without opening the dashboard.`,
  },
]

const facts = [
  {
    title: 'Payments go straight to you',
    body: `Payment links are created on your own Razorpay or Cashfree account, so buyers pay you directly. You add your API keys once; ${site.name} never holds buyer money.`,
  },
  {
    title: 'No website needed',
    body: 'Add products and collections in the dashboard and share your WhatsApp store link. Buyers shop inside the chat.',
  },
  {
    title: 'WhatsApp’s catalog, when you want it',
    body: 'You can also sync products to a Meta catalog for WhatsApp’s native shopping view. Meta reviews catalogs and products against its commerce policies, so it may take time to become available.',
  },
]

export function SellOnWhatsApp() {
  const stageRef = useRef<HTMLDivElement>(null)
  const onScreen = useOnScreen(stageRef)
  const { step, autoplay, runKey, jumpTo } = useShopSequence(onScreen)
  const animate = !usePrefersReducedMotion()
  /** The step described under the phone-sized step chips (the first one before autoplay starts). */
  const shown = Math.max(step, 0)

  return (
    <section id="sell" className="border-t border-line bg-paper-2/50 py-16 md:py-28">
      <Container>
        <SectionHeader
          index="05"
          eyebrow="Sell on WhatsApp"
          title="Your shop, inside the chat your buyers already use."
          description="Buyers browse, order and track deliveries on WhatsApp, and pay through a payment link or cash on delivery. You manage orders from the dashboard or straight from your phone."
        />

        <div className="mt-10 grid grid-cols-1 items-center gap-6 md:mt-14 md:gap-12 lg:grid-cols-12 lg:gap-10">
          <Reveal className="min-w-0 lg:col-span-5">
            <p className="mb-3 font-mono text-[12px] uppercase tracking-[0.12em] text-muted md:text-[11px]">
              <span className="md:hidden">Select a step</span>
              <span className="max-md:hidden">Select a step to show it on the phones</span>
            </p>
            {/* Phones: the steps are a row of numbered chips; the current step's text shows below them. */}
            <ol className="shop-steps">
              {steps.map((item, i) => {
                const state = i < step ? 'done' : i === step ? 'current' : 'upcoming'
                return (
                  <li
                    key={item.title}
                    data-state={state}
                    className={cn(
                      'shop-step group relative grid grid-cols-[2.25rem_minmax(0,1fr)] gap-x-3 rounded-r-md border-l-2 py-3 pl-4 pr-2 transition-colors duration-500',
                      'has-[button:focus-visible]:outline-2 has-[button:focus-visible]:outline-offset-2 has-[button:focus-visible]:outline-accent',
                      state === 'current' ? 'border-accent bg-card/70' : 'border-line hover:border-muted hover:bg-card/40',
                    )}
                  >
                    <span
                      className={cn(
                        'shop-step-number pt-0.5 font-mono text-[12px]',
                        state === 'upcoming' ? 'text-muted' : 'text-accent-2',
                      )}
                    >
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <div className="shop-step-text">
                      <h3 className="text-[16px] font-semibold tracking-[-0.01em]">
                        {/* The button's hit area stretches over the whole step (the whole chip on phones). */}
                        <button
                          type="button"
                          aria-current={state === 'current' ? 'step' : undefined}
                          onClick={() => jumpTo(i)}
                          className="cursor-pointer text-left after:absolute after:inset-0 after:content-[''] focus-visible:outline-none"
                        >
                          <span className="max-md:sr-only">{item.title}</span>
                        </button>
                      </h3>
                      <p className="mt-1 text-[14.5px] leading-relaxed text-muted max-md:hidden">{item.body}</p>
                      {state === 'current' && (
                        <StepProgress key={runKey} autoplay={autoplay} className="mt-3 max-md:hidden" />
                      )}
                    </div>
                  </li>
                )
              })}
            </ol>
            <div className="mt-4 min-h-[10.5rem] md:hidden" data-shop-step-detail="">
              <p className="font-mono text-[12px] uppercase tracking-[0.12em] text-accent-2">
                Step {shown + 1} of {steps.length}
              </p>
              {/* The step button already announces the title. */}
              <p aria-hidden="true" className="mt-1 text-[17px] font-semibold tracking-[-0.01em]">
                {steps[shown].title}
              </p>
              <p className="mt-1 text-[15px] leading-relaxed text-muted">{steps[shown].body}</p>
              {step >= 0 && <StepProgress key={runKey} autoplay={autoplay} className="mt-3" />}
            </div>
          </Reveal>

          <Reveal delay={120} className="min-w-0 lg:col-span-7">
            <div
              ref={stageRef}
              data-shop-step={step}
              data-shop-autoplay={autoplay}
              data-paused={onScreen ? undefined : ''}
            >
              <ShopJourneyMockup step={step} animate={animate} />
            </div>
          </Reveal>
        </div>

        <Reveal className="mt-10 md:mt-16">
          <SwipeRow
            label="How selling works"
            itemName="fact"
            className="grid gap-px overflow-hidden rounded-xl border border-line bg-line md:grid-cols-3"
          >
            {facts.map((fact) => (
              <li key={fact.title} className="bg-card p-5 max-md:rounded-xl max-md:border max-md:border-line md:p-6">
                <h3 className="text-[17px] font-semibold tracking-[-0.01em]">{fact.title}</h3>
                <p className="mt-2 text-[14.5px] leading-relaxed text-muted">{fact.body}</p>
              </li>
            ))}
          </SwipeRow>
        </Reveal>

        <p className="mt-6 max-w-3xl text-[13px] leading-relaxed text-muted">
          Shop replies inside the buyer’s 24-hour customer service window are free under Meta’s current pricing. Order
          updates sent after the window closes use utility templates, which Meta charges to your own WhatsApp Business
          Account.
        </p>
      </Container>
    </section>
  )
}

/** Fills over the current step's autoplay time; keyed by `runKey` so each fresh countdown restarts it. */
function StepProgress({ autoplay, className }: { autoplay: ShopAutoplay; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn('shop-progress', className)}
      data-progress={autoplay}
      style={{ '--step-ms': `${SHOP_STEP_MS}ms` } as CSSProperties}
    >
      <span />
    </span>
  )
}
