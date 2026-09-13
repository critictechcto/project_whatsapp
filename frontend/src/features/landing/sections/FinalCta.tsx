import { ArrowRight } from 'lucide-react'
import { Button } from '../../../components/ui/Button'
import { Container } from '../../../components/ui/Container'
import { Reveal } from '../../../components/ui/Reveal'
import { site } from '../../../config/site'

export function FinalCta() {
  return (
    <section className="pb-20 md:pb-28">
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
          <div className="relative max-w-3xl">
            <h2 className="font-display text-[2.2rem] font-semibold leading-[1.05] tracking-[-0.035em] text-balance md:text-[3.4rem]">
              Start sending messages your customers are glad to get.
            </h2>
            <p className="mt-5 max-w-xl text-[17px] leading-relaxed text-paper/70">
              Connect your number today and send your first approved template this afternoon.
            </p>
            <div className="mt-9 flex flex-wrap gap-3">
              <Button href={site.links.signup} variant="inverse" size="lg">
                Start {site.trialDays}-day free trial
                <ArrowRight className="size-4 transition-transform duration-300 group-hover:translate-x-0.5" aria-hidden="true" />
              </Button>
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
