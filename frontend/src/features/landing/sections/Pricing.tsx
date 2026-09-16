import { useEffect, useRef, useState } from 'react'
import { ArrowRight, Check } from 'lucide-react'
import { Button } from '../../../components/ui/Button'
import { Container } from '../../../components/ui/Container'
import { MagneticButton } from '../../../components/ui/MagneticButton'
import { Reveal } from '../../../components/ui/Reveal'
import { SectionHeader } from '../../../components/ui/SectionHeader'
import { TiltCard } from '../../../components/ui/TiltCard'
import { ANNUAL_MONTHS_CHARGED, plans, site } from '../../../config/site'
import { cn } from '../../../lib/cn'
import { formatINR } from '../../../lib/format'
import { prefersReducedMotion } from '../../../lib/motion'
import { useOnScreen } from '../lib/useOnScreen'
import './Pricing.css'

type Billing = 'monthly' | 'annual'

/**
 * Rolls a number from whatever it currently shows to `target` with an ease-out curve and always lands
 * exactly on `target`. It starts on `target` (no roll on first render); reduced motion jumps straight there.
 */
function useRolledNumber(target: number, duration = 700) {
  const [value, setValue] = useState(target)
  const shownRef = useRef(target)

  useEffect(() => {
    const from = shownRef.current
    if (from === target) return
    if (prefersReducedMotion()) {
      shownRef.current = target
      setValue(target)
      return
    }

    let frame = 0
    let startedAt: number | null = null
    const tick = (now: number) => {
      startedAt ??= now
      const progress = Math.min((now - startedAt) / duration, 1)
      const next = progress === 1 ? target : Math.round(from + (target - from) * (1 - Math.pow(1 - progress, 3)))
      shownRef.current = next
      setValue(next)
      if (progress < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [target, duration])

  return value
}

/** The visible figure rolls; screen readers get only the settled price. */
function PlanPrice({ amount }: { amount: number }) {
  const shown = useRolledNumber(amount)

  return (
    <>
      <span
        aria-hidden="true"
        data-testid="plan-price"
        data-rolling={shown !== amount}
        className="pricing-amount font-display text-[2.7rem] font-semibold leading-none tracking-[-0.035em] tabular-nums"
      >
        {formatINR(shown)}
      </span>
      <span className="sr-only">{formatINR(amount)}</span>
    </>
  )
}

export function Pricing() {
  const [billing, setBilling] = useState<Billing>('annual')
  const listRef = useRef<HTMLUListElement | null>(null)
  const listOnScreen = useOnScreen(listRef)

  return (
    <section id="pricing" className="border-t border-line bg-paper-2/50 py-20 md:py-28">
      <Container>
        <div className="flex flex-col justify-between gap-8 lg:flex-row lg:items-end">
          <SectionHeader
            index="09"
            eyebrow="Pricing"
            title="Simple plans. Meta’s fees at cost."
            description={`Every plan includes a ${site.trialDays}-day free trial with no card required. Prices are in INR and exclude ${site.gstRate}% GST.`}
          />
          <div
            role="group"
            aria-label="Billing period"
            className="relative inline-grid shrink-0 grid-cols-2 self-start rounded-lg border border-line bg-card p-1 lg:self-auto"
          >
            <span
              aria-hidden="true"
              className={cn(
                'absolute inset-y-1 left-1 w-[calc(50%-0.25rem)] rounded-md bg-ink transition-transform duration-300 ease-soft',
                billing === 'annual' && 'translate-x-full',
              )}
            />
            {(['monthly', 'annual'] as const).map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={billing === option}
                onClick={() => setBilling(option)}
                className={cn(
                  'relative rounded-md px-4 py-2 text-[14px] font-medium transition-colors duration-300',
                  billing === option ? 'text-paper' : 'text-muted hover:text-ink',
                )}
              >
                {option === 'monthly' ? 'Monthly' : 'Annual · 2 months free'}
              </button>
            ))}
          </div>
        </div>

        <ul ref={listRef} className="mt-14 grid gap-5 lg:grid-cols-3">
          {plans.map((plan, i) => {
            const annualTotal = plan.monthlyPrice * ANNUAL_MONTHS_CHARGED
            const shownPrice = billing === 'monthly' ? plan.monthlyPrice : Math.round(annualTotal / 12)

            return (
              <Reveal as="li" key={plan.id} delay={i * 100} className="flex">
                {/* The recommended plan floats a little forward; the lift lives on its own layer so it
                    composes with the Reveal rise and the TiltCard tilt. */}
                <div
                  className={cn('flex w-full', plan.recommended && 'pricing-lift')}
                  data-on-screen={plan.recommended ? listOnScreen : undefined}
                >
                  <TiltCard
                    max={plan.recommended ? 4 : 3}
                    className={cn(
                      'flex w-full flex-col rounded-xl border bg-card p-7',
                      plan.recommended ? 'border-ink shadow-[0_24px_48px_-32px_rgba(16,39,31,0.45)]' : 'border-line',
                    )}
                  >
                    {plan.recommended && (
                      <span className="absolute -top-3 left-7 rounded bg-ink px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-paper">
                        Recommended
                      </span>
                    )}
                    <h3 className="text-[18px] font-semibold">{plan.name}</h3>
                    <p className="mt-1.5 text-[14.5px] text-muted">{plan.blurb}</p>

                    <p className="mt-7 flex items-baseline gap-1.5">
                      <PlanPrice amount={shownPrice} />
                      <span className="text-[14px] text-muted">/ month</span>
                    </p>
                    <p key={`${billing}-note`} className="fade-up mt-2 h-5 text-[13px] text-muted">
                      {billing === 'annual' ? `Billed ${formatINR(annualTotal)} yearly` : 'Billed monthly, cancel anytime'}
                    </p>

                    {plan.recommended ? (
                      <MagneticButton
                        href={site.links.signup}
                        variant="primary"
                        max={6}
                        wrapperClassName="mt-7 flex"
                        className="w-full"
                      >
                        Start free trial
                      </MagneticButton>
                    ) : (
                      <Button href={site.links.signup} variant="secondary" className="mt-7 w-full">
                        Start free trial
                      </Button>
                    )}

                    <ul className="mt-7 space-y-1.5 border-t border-line pt-6 text-[14px] font-medium">
                      {plan.limits.map((limit) => (
                        <li key={limit}>{limit}</li>
                      ))}
                    </ul>
                    <ul className="mt-5 space-y-2.5 text-[14px] text-muted">
                      {plan.features.map((feature) => (
                        <li key={feature} className="flex gap-2.5">
                          <Check className="mt-0.5 size-4 shrink-0 text-accent-2" aria-hidden="true" />
                          {feature}
                        </li>
                      ))}
                    </ul>
                  </TiltCard>
                </div>
              </Reveal>
            )
          })}
        </ul>

        <Reveal className="mt-5 flex flex-col justify-between gap-5 rounded-xl border border-line bg-card p-7 md:flex-row md:items-center">
          <div>
            <h3 className="text-[18px] font-semibold">Enterprise</h3>
            <p className="mt-1.5 max-w-2xl text-[14.5px] text-muted">
              Custom number and seat limits, dedicated onboarding, SLA, invoicing on purchase order and help with Meta
              business verification.
            </p>
          </div>
          <Button href={site.links.contactSales} variant="secondary" className="shrink-0">
            Talk to sales
            <ArrowRight className="size-4 transition-transform duration-300 group-hover:translate-x-0.5" aria-hidden="true" />
          </Button>
        </Reveal>

        <Reveal as="aside" className="mt-10 grid gap-8 border-t border-line pt-10 md:grid-cols-12">
          <div className="md:col-span-4">
            <h3 className="font-display text-[1.55rem] font-semibold leading-[1.1] tracking-[-0.025em]">
              About Meta’s message charges
            </h3>
          </div>
          <dl className="grid gap-6 text-[14.5px] sm:grid-cols-3 md:col-span-8">
            <div>
              <dt className="font-medium">Billed separately</dt>
              <dd className="mt-1.5 leading-relaxed text-muted">
                Meta charges for template messages by category. These charges are separate from your {site.name} plan.
              </dd>
            </div>
            <div>
              <dt className="font-medium">Passed on at cost</dt>
              <dd className="mt-1.5 leading-relaxed text-muted">
                You pay Meta’s published rate for India. We don’t add a markup, and every campaign shows an estimate
                first.
              </dd>
            </div>
            <div>
              <dt className="font-medium">Replies are free</dt>
              <dd className="mt-1.5 leading-relaxed text-muted">
                Under Meta’s current pricing, replying to customers inside the 24-hour service window costs nothing.
              </dd>
            </div>
          </dl>
        </Reveal>
      </Container>
    </section>
  )
}
