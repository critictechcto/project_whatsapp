import { useId, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { Container } from '../../../components/ui/Container'
import { Reveal } from '../../../components/ui/Reveal'
import { SectionHeader } from '../../../components/ui/SectionHeader'
import { site } from '../../../config/site'
import { cn } from '../../../lib/cn'
import { useInView } from '../../../lib/useInView'
import { SwipeRow } from './SwipeRow'

const categories = [
  {
    name: 'Marketing',
    kind: 'Template',
    examples: 'Offers, new arrivals, festive sales, event invites, win-back messages',
    charge: 'Charged by Meta per delivered message',
  },
  {
    name: 'Utility',
    kind: 'Template',
    examples: 'Order and delivery updates, payment reminders, appointment confirmations',
    charge: 'Charged by Meta, but free inside an open customer service window',
  },
  {
    name: 'Authentication',
    kind: 'Template',
    examples: 'One-time passcodes for login, sign-up and payment verification',
    charge: 'Charged by Meta per delivered message',
  },
  {
    name: 'Service',
    kind: 'Free-form reply',
    examples: 'Any reply to a customer who messaged you within the last 24 hours',
    charge: 'Free under Meta’s current pricing',
  },
]

/** Timeline of the 24-hour window; the open-window bar grows in when scrolled into view. */
function ServiceWindowTimeline() {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.4 })
  const bar = 'transition-transform duration-[1400ms] ease-soft'
  const endDot = cn(
    'shrink-0 rounded-full border-2 border-ink bg-card transition-[opacity,scale] duration-500 delay-[1200ms]',
    inView ? 'scale-100 opacity-100' : 'scale-50 opacity-0',
  )

  return (
    <div ref={ref} className="flex h-full flex-col justify-center" aria-hidden="true">
      <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-6 sm:grid-cols-1 sm:gap-y-3">
        <div className="relative flex flex-col items-center sm:hidden">
          <span className="size-3 rounded-full bg-ink" />
          <span className={cn('w-2 flex-1 origin-top rounded-full bg-accent', bar, inView ? 'scale-y-100' : 'scale-y-0')} />
          <span className={cn('size-3', endDot)} />
          <span className="h-12 w-2 rounded-full bg-line" />
        </div>

        <div className="hidden h-3 sm:flex sm:items-center">
          <span className="size-3 shrink-0 rounded-full bg-ink" />
          <span className={cn('h-2 flex-[3] origin-left bg-accent', bar, inView ? 'scale-x-100' : 'scale-x-0')} />
          <span className={cn('size-3', endDot)} />
          <span className="h-2 flex-[1.4] rounded-r-full bg-line" />
        </div>

        <div className="flex flex-col justify-between gap-6 text-[13.5px] sm:flex-row sm:gap-4">
          <div className="sm:w-[20%]">
            <p className="font-medium">Customer messages you</p>
            <p className="font-mono text-[12px] text-muted sm:text-[11.5px]">Hour 0</p>
          </div>
          <div className="sm:w-[40%]">
            <p className="font-medium text-accent-2">Window open — reply freely</p>
            <p className="text-muted">Text, media, documents, buttons. Service replies are free.</p>
          </div>
          <div className="sm:w-[40%] sm:text-right">
            <p className="font-medium">After 24 hours</p>
            <p className="text-muted">Only an approved template can reopen the conversation.</p>
          </div>
        </div>
      </div>
    </div>
  )
}

/**
 * A rule's eyebrow and title. From md up it is plain text; below md it is a disclosure button that
 * shows or hides the rule's body (the elements whose ids are in `controls`).
 */
function RuleHeading({
  number,
  title,
  open,
  onToggle,
  controls,
}: {
  number: number
  title: string
  open: boolean
  onToggle: () => void
  controls: string
}) {
  return (
    <>
      <h3 className="md:hidden">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={controls}
          onClick={onToggle}
          className="-m-2 flex w-[calc(100%+1rem)] cursor-pointer items-center justify-between gap-4 rounded-lg p-2 text-left focus-visible:outline-2 focus-visible:outline-accent"
        >
          <span>
            <span className="block font-mono text-[12px] uppercase tracking-[0.14em] text-accent-2">Rule {number}</span>
            <span className="mt-2 block text-[20px] font-semibold leading-snug tracking-[-0.01em]">{title}</span>
          </span>
          <ChevronDown
            aria-hidden="true"
            className={cn('size-5 shrink-0 text-muted transition-transform duration-300', open && 'rotate-180')}
          />
        </button>
      </h3>
      <div className="max-md:hidden">
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-accent-2">Rule {number}</p>
        <h3 className="mt-2 text-[20px] font-semibold tracking-[-0.01em]">{title}</h3>
      </div>
    </>
  )
}

export function MessagingRules() {
  const baseId = useId()
  const id = (name: string) => `${baseId}-${name}`
  // Phones show the rules as disclosures with the first one open; md and up always show every rule.
  const [open, setOpen] = useState<Record<number, boolean>>({ 1: true })
  const toggle = (rule: number) => () => setOpen((current) => ({ ...current, [rule]: !current[rule] }))
  const body = (rule: number) => (open[rule] ? undefined : 'max-md:hidden')

  return (
    <section id="rules" className="border-t border-line bg-paper-2/50 py-16 md:py-28">
      <Container>
        <SectionHeader
          index="07"
          eyebrow="WhatsApp’s rules, explained"
          title="The rules Meta sets — and how we handle them for you."
          description="WhatsApp protects its users from spam with a few clear rules. Understanding them up front saves you from rejected templates, blocked messages and surprise bills."
        />

        <Reveal as="article" className="mt-10 rounded-xl border border-line bg-card p-5 md:mt-14 md:p-8">
          <div className="grid gap-6 md:gap-8 lg:grid-cols-12">
            <div className="lg:col-span-4">
              <RuleHeading
                number={1}
                title="The 24-hour customer service window"
                open={!!open[1]}
                onToggle={toggle(1)}
                controls={`${id('r1-text')} ${id('r1-timeline')}`}
              />
              <p id={id('r1-text')} className={cn('mt-3 text-[15px] leading-relaxed text-muted', body(1))}>
                When a customer messages you, a 24-hour window opens. Inside it you can reply with anything — text,
                images, documents. Once it closes, you can only start a conversation with an approved template. Every
                new customer message resets the clock.
              </p>
            </div>
            <div id={id('r1-timeline')} className={cn('lg:col-span-8 lg:pl-6', body(1))}>
              <ServiceWindowTimeline />
            </div>
          </div>
        </Reveal>

        <Reveal className="mt-4 rounded-xl border border-line bg-card p-5 md:mt-6 md:p-8">
          <div className="max-w-2xl">
            <RuleHeading
              number={2}
              title="Every message has a category"
              open={!!open[2]}
              onToggle={toggle(2)}
              controls={`${id('r2-text')} ${id('r2-categories')} ${id('r2-note')}`}
            />
            <p id={id('r2-text')} className={cn('mt-3 text-[15px] leading-relaxed text-muted', body(2))}>
              Meta categorises templates by purpose, and the category decides what you pay. Choosing the right one
              matters: Meta can re-categorise a template that doesn’t match its content.
            </p>
          </div>
          <div id={id('r2-categories')} className={body(2)}>
            <SwipeRow
              as="div"
              label="Message categories"
              itemName="category"
              wrapperClassName="mt-6 md:mt-8"
              className="grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-2 lg:grid-cols-4"
            >
              {categories.map((category) => (
                <div
                  key={category.name}
                  className="flex flex-col bg-card p-5 max-md:rounded-lg max-md:border max-md:border-line"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
                    <h4 className="font-display text-[1.3rem] font-semibold leading-none tracking-[-0.02em]">
                      {category.name}
                    </h4>
                    <span className="font-mono text-[12px] uppercase tracking-[0.1em] text-muted md:text-[10.5px]">
                      {category.kind}
                    </span>
                  </div>
                  <p className="mt-4 flex-1 text-[14px] leading-relaxed text-muted">{category.examples}</p>
                  <p className="mt-5 border-t border-line-2 pt-3 text-[13px] font-medium">{category.charge}</p>
                </div>
              ))}
            </SwipeRow>
          </div>
          <p id={id('r2-note')} className={cn('mt-4 text-[13px] text-muted', body(2))}>
            Meta publishes rates per country and updates them periodically. {site.name} shows the current rate for India
            in your dashboard and estimates the cost of each campaign before you send it.
          </p>
        </Reveal>

        <div className="mt-4 grid gap-4 md:mt-6 md:grid-cols-2 md:gap-6">
          <Reveal as="article" className="rounded-xl border border-line bg-card p-5 md:p-8">
            <RuleHeading
              number={3}
              title="Customers must opt in"
              open={!!open[3]}
              onToggle={toggle(3)}
              controls={id('r3-body')}
            />
            <div id={id('r3-body')} className={body(3)}>
              <p className="mt-3 text-[15px] leading-relaxed text-muted">
                You can only send business-initiated messages to people who agreed to receive them on WhatsApp — through
                a checkbox at checkout, a website form, a click-to-chat ad or a signed form in store. Bought or scraped
                lists are not allowed.
              </p>
              <p className="mt-4 border-t border-line-2 pt-4 text-[14px]">
                <span className="font-medium">How we help:</span>{' '}
                <span className="text-muted">
                  every contact stores its opt-in source and date, and replies like “STOP” opt people out automatically.
                </span>
              </p>
            </div>
          </Reveal>
          <Reveal as="article" delay={100} className="rounded-xl border border-line bg-card p-5 md:p-8">
            <RuleHeading
              number={4}
              title="Quality affects your limits"
              open={!!open[4]}
              onToggle={toggle(4)}
              controls={id('r4-body')}
            />
            <div id={id('r4-body')} className={body(4)}>
              <p className="mt-3 text-[15px] leading-relaxed text-muted">
                Meta gives each number a quality rating based on how customers react. Many blocks or spam reports can
                lower your sending limit or pause a template. Relevant, expected messages keep the rating high.
              </p>
              <p className="mt-4 border-t border-line-2 pt-4 text-[14px]">
                <span className="font-medium">How we help:</span>{' '}
                <span className="text-muted">
                  we show each number’s quality rating and warn you early when it starts to drop.
                </span>
              </p>
            </div>
          </Reveal>
        </div>
      </Container>
    </section>
  )
}
