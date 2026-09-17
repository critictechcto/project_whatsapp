import { useRef, type CSSProperties } from 'react'
import { ArrowRight, CheckCheck } from 'lucide-react'
import { Button } from '../../../components/ui/Button'
import { Container } from '../../../components/ui/Container'
import { MagneticButton } from '../../../components/ui/MagneticButton'
import { Reveal } from '../../../components/ui/Reveal'
import { SplitReveal } from '../../../components/ui/SplitReveal'
import { usePointerTilt } from '../../../components/ui/usePointerTilt'
import { site } from '../../../config/site'
import { useOnScreen } from '../lib/useOnScreen'
import './FinalCta.css'

type Bubble = {
  text: string
  side: 'in' | 'out'
  left: string
  top: string
  /** Depth in px; nearer bubbles move more with the pointer. */
  z: number
  delay: number
  time: string
}

// Example conversations of the kind the product sends; illustrative, not real customers.
const bubbles: Bubble[] = [
  { text: 'Hi! Is the blue kurta available in M?', side: 'in', left: '8%', top: '12%', z: 30, delay: 0, time: '10:02' },
  { text: 'Yes — tap below to add it to your cart.', side: 'out', left: '30%', top: '31%', z: 90, delay: 1.2, time: '10:02' },
  { text: 'Reminder: your appointment is tomorrow at 11:30.', side: 'out', left: '14%', top: '55%', z: 10, delay: 2.4, time: '09:00' },
  { text: 'Paid ₹540. Thank you!', side: 'in', left: '34%', top: '76%', z: 60, delay: 0.6, time: '18:45' },
]

/** CSS 3D chat bubbles that drift with the pointer (fine pointers only) and bob while on screen. */
function CtaBubbles() {
  const rootRef = useRef<HTMLDivElement | null>(null)
  const playing = useOnScreen(rootRef)
  const sceneRef = usePointerTilt<HTMLDivElement>({ max: 7, track: 'section' })

  return (
    <div ref={rootRef} aria-hidden="true" data-playing={playing} className="cta-bubbles hidden select-none xl:block">
      <div ref={sceneRef} className="cta-bubbles-scene">
        {bubbles.map((bubble) => (
          <div
            key={bubble.text}
            className="cta-bubble"
            data-side={bubble.side}
            style={
              {
                '--bubble-left': bubble.left,
                '--bubble-top': bubble.top,
                '--bubble-z': `${bubble.z}px`,
                '--bubble-delay': `${-bubble.delay}s`,
              } as CSSProperties
            }
          >
            <div>
              {bubble.text}
              <span className="ml-2 inline-flex translate-y-0.5 items-center gap-0.5 font-mono text-[10px] text-muted">
                {bubble.time}
                {bubble.side === 'out' && <CheckCheck className="size-3 text-accent" />}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function FinalCta() {
  return (
    <section className="pb-16 md:pb-28">
      <Container>
        <Reveal className="relative overflow-hidden rounded-2xl bg-ink px-6 py-14 text-paper md:px-14 md:py-20">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -right-24 -top-24 size-80 rounded-full border border-paper/10"
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -right-8 -top-8 size-48 rounded-full border border-paper/10"
          />
          <CtaBubbles />
          <div className="relative max-w-3xl xl:max-w-[40rem]">
            <SplitReveal className="font-display text-[2.2rem] font-semibold leading-[1.05] tracking-[-0.035em] text-balance md:text-[3.4rem]">
              Start sending messages your customers are glad to get.
            </SplitReveal>
            <p className="mt-5 max-w-xl text-[17px] leading-relaxed text-paper/70">
              Connect your number today and send your first approved template this afternoon.
            </p>
            <div className="mt-9 flex flex-wrap gap-3">
              <MagneticButton href={site.links.signup} variant="inverse" size="lg">
                Start {site.trialDays}-day free trial
                <ArrowRight className="size-4 transition-transform duration-300 group-hover:translate-x-0.5" aria-hidden="true" />
              </MagneticButton>
              <Button href={site.links.contactSales} variant="outline-inverse" size="lg">
                Talk to sales
              </Button>
            </div>
            <p className="mt-6 font-mono text-[12px] text-paper/60">No card required · Cancel anytime · Setup help included</p>
          </div>
        </Reveal>
      </Container>
    </section>
  )
}
