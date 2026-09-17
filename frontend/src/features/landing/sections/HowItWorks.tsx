import { useId, useState } from 'react'
import { Check, ChevronDown } from 'lucide-react'
import { Container } from '../../../components/ui/Container'
import { Reveal } from '../../../components/ui/Reveal'
import { ScrollDepth } from '../../../components/ui/ScrollDepth'
import { SectionHeader } from '../../../components/ui/SectionHeader'
import { site } from '../../../config/site'
import { cn } from '../../../lib/cn'
import { EmbeddedSignupMockup } from '../mockups/EmbeddedSignupMockup'
import { MessageJourney } from '../scenes/MessageJourney'

const steps = [
  {
    title: 'Create your workspace',
    time: '2 min',
    body: 'Sign up with your email, name your business and invite the teammates who will reply to customers.',
  },
  {
    title: 'Connect WhatsApp with Meta',
    time: '~5 min',
    body: 'Click “Connect WhatsApp”. Meta’s secure popup walks you through your business portfolio, phone number and a one-time code.',
  },
  {
    title: 'Add contacts & templates',
    time: 'Same day',
    body: 'Import opted-in contacts from CSV and create message templates. Meta usually reviews templates within minutes.',
  },
  {
    title: 'Send, schedule, automate',
    time: 'Ongoing',
    body: 'Launch campaigns, schedule reminders, set up auto-replies and answer every response from the shared inbox.',
  },
]

const receives = [
  'Your WhatsApp Business Account ID',
  'The phone number ID you selected',
  'An access token to send messages for you — stored encrypted',
]

export function HowItWorks() {
  // Phones collapse the Embedded Signup detail behind a disclosure; md and up always show it.
  const [detailsOpen, setDetailsOpen] = useState(false)
  const detailsId = useId()

  return (
    <section id="how-it-works" className="border-y border-line bg-paper-2/50 py-12 md:py-28">
      <Container>
        <SectionHeader
          index="02"
          eyebrow="How it works"
          title="From sign-up to first message in one afternoon."
          description="No developer account, no API keys to copy, no waiting on a sales call. Setup runs through Meta’s official Embedded Signup, so your number is connected the way Meta intends."
        />

        <Reveal className="mt-10 md:mt-14">
          {/* Phones: a swipe row of step cards with the next card peeking in; md and up: the grid. */}
          <ol
            tabIndex={0}
            aria-label="Setup steps"
            className="-mx-5 flex snap-x snap-mandatory scroll-px-5 gap-3 overflow-x-auto px-5 pb-2 md:mx-0 md:grid md:snap-none md:gap-px md:overflow-hidden md:rounded-xl md:border md:border-line md:bg-line md:p-0 md:grid-cols-2 lg:grid-cols-4"
          >
            {steps.map((step, i) => (
              <li
                key={step.title}
                className="flex w-[84%] shrink-0 snap-start flex-col rounded-xl border border-line bg-card p-5 md:w-auto md:rounded-none md:border-0 md:p-6"
              >
                <div className="flex items-baseline justify-between">
                  <span className="font-display text-[1.9rem] font-medium leading-none tracking-[-0.04em] text-accent-2 md:text-[2.2rem]">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span className="font-mono text-[12px] text-muted md:text-[11px]">{step.time}</span>
                </div>
                <h3 className="mt-4 text-[17px] font-semibold tracking-[-0.01em] md:mt-6">{step.title}</h3>
                <p className="mt-2 text-[14.5px] leading-relaxed text-muted">{step.body}</p>
              </li>
            ))}
          </ol>
        </Reveal>

        <div className="mt-10 md:mt-20">
          <Reveal className="max-w-2xl">
            <h3 className="font-display text-[1.5rem] font-semibold leading-[1.1] tracking-[-0.025em] md:text-[2rem]">
              What happens when you hit send
            </h3>
            <p className="mt-4 text-[15px] leading-relaxed text-muted md:mt-5 md:text-[16px]">
              Every message passes through {site.name} and Meta’s WhatsApp Cloud API before it reaches your customer.
              Meta then reports its status back, so you can see what was delivered and read.
            </p>
          </Reveal>
          <div className="mt-6 md:mt-10">
            <MessageJourney />
          </div>
          <p className="mt-4 text-[13px] text-muted md:mt-8">
            Read status is only reported when the customer has read receipts turned on in WhatsApp.
          </p>
        </div>

        <div className="mt-10 grid grid-cols-1 items-center gap-8 md:mt-20 md:gap-12 lg:grid-cols-12 lg:gap-10">
          <Reveal className="min-w-0 lg:col-span-5">
            <h3 className="font-display text-[1.5rem] font-semibold leading-[1.1] tracking-[-0.025em] md:text-[2rem]">
              What happens when you click “Connect WhatsApp”
            </h3>
            <button
              type="button"
              aria-expanded={detailsOpen}
              aria-controls={detailsId}
              onClick={() => setDetailsOpen((open) => !open)}
              className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-md border border-line bg-card px-4 text-[15px] font-medium shadow-[inset_0_1px_0_rgb(255_255_255/0.9),0_2px_0_var(--color-line)] md:hidden"
            >
              {detailsOpen ? 'Hide the details' : 'Show the details'}
              <ChevronDown
                className={cn('size-4 transition-transform duration-200', detailsOpen && 'rotate-180')}
                aria-hidden="true"
              />
            </button>
            <div id={detailsId} className={cn(!detailsOpen && 'max-md:hidden')}>
              <p className="mt-5 text-[16px] leading-relaxed text-muted">
                Meta’s Embedded Signup opens in a secure popup. You sign in with Facebook directly on Meta —{' '}
                {site.name} never sees your password — and give our app permission to send messages for your WhatsApp
                Business Account. You can remove that permission at any time from Meta Business settings.
              </p>
              <p className="mt-6 font-mono text-[12px] uppercase tracking-[0.14em] text-muted md:text-[11px]">
                What {site.name} receives
              </p>
              <ul className="mt-3 space-y-2.5 text-[15px]">
                {receives.map((item) => (
                  <li key={item} className="flex gap-2.5">
                    <Check className="mt-0.5 size-4 shrink-0 text-accent-2" aria-hidden="true" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
          <Reveal
            delay={120}
            className={cn('min-w-0 lg:col-span-6 lg:col-start-7', !detailsOpen && 'max-md:hidden')}
          >
            <ScrollDepth>
              <EmbeddedSignupMockup />
            </ScrollDepth>
          </Reveal>
        </div>
      </Container>
    </section>
  )
}
