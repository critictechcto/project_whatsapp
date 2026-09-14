import { Container } from '../../../components/ui/Container'
import { Reveal } from '../../../components/ui/Reveal'
import { SectionHeader } from '../../../components/ui/SectionHeader'
import { site } from '../../../config/site'
import { cn } from '../../../lib/cn'
import { useInView } from '../../../lib/useInView'

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
          <span className="h-16 w-2 rounded-full bg-line" />
        </div>

        <div className="hidden h-3 sm:flex sm:items-center">
          <span className="size-3 shrink-0 rounded-full bg-ink" />
          <span className={cn('h-2 flex-[3] origin-left bg-accent', bar, inView ? 'scale-x-100' : 'scale-x-0')} />
          <span className={cn('size-3', endDot)} />
          <span className="h-2 flex-[1.4] rounded-r-full bg-line" />
        </div>

        <div className="flex flex-col justify-between gap-8 text-[13.5px] sm:flex-row sm:gap-4">
          <div className="sm:w-[20%]">
            <p className="font-medium">Customer messages you</p>
            <p className="font-mono text-[11.5px] text-muted">Hour 0</p>
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

export function MessagingRules() {
  return (
    <section id="rules" className="border-t border-line bg-paper-2/50 py-20 md:py-28">
      <Container>
        <SectionHeader
          index="06"
          eyebrow="WhatsApp’s rules, explained"
          title="The rules Meta sets — and how we handle them for you."
          description="WhatsApp protects its users from spam with a few clear rules. Understanding them up front saves you from rejected templates, blocked messages and surprise bills."
        />

        <Reveal as="article" className="mt-14 rounded-xl border border-line bg-card p-6 md:p-8">
          <div className="grid gap-8 lg:grid-cols-12">
            <div className="lg:col-span-4">
              <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-accent-2">Rule 1</p>
              <h3 className="mt-2 text-[20px] font-semibold tracking-[-0.01em]">The 24-hour customer service window</h3>
              <p className="mt-3 text-[15px] leading-relaxed text-muted">
                When a customer messages you, a 24-hour window opens. Inside it you can reply with anything — text,
                images, documents. Once it closes, you can only start a conversation with an approved template. Every
                new customer message resets the clock.
              </p>
            </div>
            <div className="lg:col-span-8 lg:pl-6">
              <ServiceWindowTimeline />
            </div>
          </div>
        </Reveal>

        <Reveal className="mt-6 rounded-xl border border-line bg-card p-6 md:p-8">
          <div className="max-w-2xl">
            <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-accent-2">Rule 2</p>
            <h3 className="mt-2 text-[20px] font-semibold tracking-[-0.01em]">Every message has a category</h3>
            <p className="mt-3 text-[15px] leading-relaxed text-muted">
              Meta categorises templates by purpose, and the category decides what you pay. Choosing the right one
              matters: Meta can re-categorise a template that doesn’t match its content.
            </p>
          </div>
          <div className="mt-8 grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
            {categories.map((category) => (
              <div key={category.name} className="flex flex-col bg-card p-5">
                <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
                  <h4 className="font-display text-[1.3rem] font-semibold leading-none tracking-[-0.02em]">
                    {category.name}
                  </h4>
                  <span className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-muted">{category.kind}</span>
                </div>
                <p className="mt-4 flex-1 text-[14px] leading-relaxed text-muted">{category.examples}</p>
                <p className="mt-5 border-t border-line-2 pt-3 text-[13px] font-medium">{category.charge}</p>
              </div>
            ))}
          </div>
          <p className="mt-4 text-[13px] text-muted">
            Meta publishes rates per country and updates them periodically. {site.name} shows the current rate for India
            in your dashboard and estimates the cost of each campaign before you send it.
          </p>
        </Reveal>

        <div className="mt-6 grid gap-6 md:grid-cols-2">
          <Reveal as="article" className="rounded-xl border border-line bg-card p-6 md:p-8">
            <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-accent-2">Rule 3</p>
            <h3 className="mt-2 text-[20px] font-semibold tracking-[-0.01em]">Customers must opt in</h3>
            <p className="mt-3 text-[15px] leading-relaxed text-muted">
              You can only send business-initiated messages to people who agreed to receive them on WhatsApp — through a
              checkbox at checkout, a website form, a click-to-chat ad or a signed form in store. Bought or scraped lists
              are not allowed.
            </p>
            <p className="mt-4 border-t border-line-2 pt-4 text-[14px]">
              <span className="font-medium">How we help:</span>{' '}
              <span className="text-muted">
                every contact stores its opt-in source and date, and replies like “STOP” opt people out automatically.
              </span>
            </p>
          </Reveal>
          <Reveal as="article" delay={100} className="rounded-xl border border-line bg-card p-6 md:p-8">
            <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-accent-2">Rule 4</p>
            <h3 className="mt-2 text-[20px] font-semibold tracking-[-0.01em]">Quality affects your limits</h3>
            <p className="mt-3 text-[15px] leading-relaxed text-muted">
              Meta gives each number a quality rating based on how customers react. Many blocks or spam reports can lower
              your sending limit or pause a template. Relevant, expected messages keep the rating high.
            </p>
            <p className="mt-4 border-t border-line-2 pt-4 text-[14px]">
              <span className="font-medium">How we help:</span>{' '}
              <span className="text-muted">
                we show each number’s quality rating and warn you early when it starts to drop.
              </span>
            </p>
          </Reveal>
        </div>
      </Container>
    </section>
  )
}
