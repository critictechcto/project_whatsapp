import { Check } from 'lucide-react'
import { Container } from '../../../components/ui/Container'
import { Reveal } from '../../../components/ui/Reveal'
import { SectionHeader } from '../../../components/ui/SectionHeader'
import { site } from '../../../config/site'
import { EmbeddedSignupMockup } from '../mockups/EmbeddedSignupMockup'

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
  return (
    <section id="how-it-works" className="border-y border-line bg-paper-2/50 py-20 md:py-28">
      <Container>
        <SectionHeader
          index="02"
          eyebrow="How it works"
          title="From sign-up to first message in one afternoon."
          description="No developer account, no API keys to copy, no waiting on a sales call. Setup runs through Meta’s official Embedded Signup, so your number is connected the way Meta intends."
        />

        <Reveal
          as="ol"
          className="mt-14 grid gap-px overflow-hidden rounded-xl border border-line bg-line md:grid-cols-2 lg:grid-cols-4"
        >
          {steps.map((step, i) => (
            <li key={step.title} className="flex flex-col bg-card p-6">
              <div className="flex items-baseline justify-between">
                <span className="font-display text-[2.2rem] font-medium leading-none tracking-[-0.04em] text-accent-2">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span className="font-mono text-[11px] text-muted">{step.time}</span>
              </div>
              <h3 className="mt-6 text-[17px] font-semibold tracking-[-0.01em]">{step.title}</h3>
              <p className="mt-2 text-[14.5px] leading-relaxed text-muted">{step.body}</p>
            </li>
          ))}
        </Reveal>

        <div className="mt-20 grid grid-cols-1 items-center gap-12 lg:grid-cols-12 lg:gap-10">
          <Reveal className="min-w-0 lg:col-span-5">
            <h3 className="font-display text-[1.7rem] font-semibold leading-[1.1] tracking-[-0.025em] md:text-[2rem]">
              What happens when you click “Connect WhatsApp”
            </h3>
            <p className="mt-5 text-[16px] leading-relaxed text-muted">
              Meta’s Embedded Signup opens in a secure popup. You sign in with Facebook directly on Meta — {site.name}{' '}
              never sees your password — and give our app permission to send messages for your WhatsApp Business
              Account. You can remove that permission at any time from Meta Business settings.
            </p>
            <p className="mt-6 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
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
          </Reveal>
          <Reveal delay={120} className="min-w-0 lg:col-span-6 lg:col-start-7">
            <EmbeddedSignupMockup />
          </Reveal>
        </div>
      </Container>
    </section>
  )
}
