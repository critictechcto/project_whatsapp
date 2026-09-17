import { ArrowRight, Check, ShieldCheck } from 'lucide-react'
import { Button } from '../../../components/ui/Button'
import { Container } from '../../../components/ui/Container'
import { site } from '../../../config/site'
import { HeroScene } from '../scenes/HeroScene'

const facts = [
  'Official Meta Cloud API',
  'You own your WhatsApp Business Account',
  'Meta message fees passed on at cost',
]

export function Hero() {
  return (
    <section id="top" className="relative overflow-hidden">
      <div className="bg-grid pointer-events-none absolute inset-0" aria-hidden="true" />
      <Container className="relative grid grid-cols-1 gap-8 pb-10 pt-8 md:gap-16 md:pb-24 md:pt-20 lg:grid-cols-12 lg:gap-10 lg:pb-32">
        <div className="min-w-0 lg:col-span-5 lg:pt-4">
          <p className="rise hidden items-center gap-2 rounded-full sm:inline-flex border border-line bg-card px-3 py-1 text-[12.5px] text-muted">
            <ShieldCheck className="size-3.5 text-accent-2" aria-hidden="true" />
            Built on the official WhatsApp Business Platform
          </p>

          <h1 className="rise rise-1 font-display sm:mt-5 md:mt-6 text-[2.3rem] font-semibold leading-[1.04] tracking-[-0.035em] text-balance sm:text-[3.3rem] lg:text-[3.6rem]">
            WhatsApp messaging for Indian businesses, <span className="text-accent-2">done properly.</span>
          </h1>

          <p className="rise rise-2 mt-4 max-w-xl text-[16px] md:mt-6 md:text-[17.5px] leading-relaxed text-muted">
            Connect your business number through Meta’s own signup flow, then send campaigns and reminders, sell
            through a WhatsApp menu with payment links or cash on delivery — and answer every reply from one shared
            team inbox. No QR-code workarounds. No banned numbers.
          </p>

          <div className="rise rise-3 mt-6 flex flex-wrap gap-3 md:mt-8">
            <Button href={site.links.signup} size="lg">
              Start {site.trialDays}-day free trial
              <ArrowRight className="size-4 transition-transform duration-300 group-hover:translate-x-0.5" aria-hidden="true" />
            </Button>
            <Button href="#how-it-works" size="lg" variant="secondary">
              See how it works
            </Button>
          </div>

          <ul className="rise rise-3 mt-7 grid gap-2 border-t border-line pt-5 text-[14px] md:mt-10 md:gap-3 md:pt-6 sm:grid-cols-3 sm:gap-6 lg:grid-cols-1 lg:gap-3">
            {facts.map((fact) => (
              <li key={fact} className="flex items-start gap-2.5">
                <Check className="mt-0.5 size-4 shrink-0 text-accent-2" aria-hidden="true" />
                {fact}
              </li>
            ))}
          </ul>
        </div>

        <div className="relative min-w-0 lg:col-span-7 lg:self-start">
          <HeroScene />
        </div>
      </Container>
    </section>
  )
}
