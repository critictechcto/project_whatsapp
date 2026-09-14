import { Check } from 'lucide-react'
import { Container } from '../../../components/ui/Container'
import { Reveal } from '../../../components/ui/Reveal'
import { SectionHeader } from '../../../components/ui/SectionHeader'
import { TiltCard } from '../../../components/ui/TiltCard'
import { site } from '../../../config/site'

const cards = [
  {
    title: 'Your phone number',
    points: [
      'Any number your business owns — mobile, landline or toll-free',
      'It must be able to receive a one-time code by SMS or voice call',
      'It can’t be active on WhatsApp at the same time (see coexistence)',
      'One number connects to one WhatsApp Business Account at a time',
    ],
  },
  {
    title: 'Already using WhatsApp on it?',
    points: [
      'WhatsApp Business app: keep using the app and connect the same number through Meta’s coexistence feature, where Meta supports it',
      'Personal WhatsApp: delete the WhatsApp account on that number first (chat history is lost), then connect',
      'Or simply use a different number for customer messaging',
    ],
  },
  {
    title: 'Display name',
    points: [
      'This is the business name customers see in WhatsApp',
      'It must match or clearly relate to your business or brand',
      'Meta reviews it against their display name guidelines',
      'You can request a change later if your brand changes',
    ],
  },
  {
    title: 'Coming from another provider',
    points: [
      'Your number can be moved to us without changing it',
      'Your Meta business verification stays with your business',
      'We guide you through the migration step by step',
      'Your old provider must release the number first',
    ],
  },
]

const limits: Array<[string, string, string]> = [
  ['Start sending messages', 'Yes', 'Yes'],
  ['Replying to customers who message you', 'Not limited by tier', 'Not limited by tier'],
  ['Business-initiated messages', 'Up to 250 unique customers per 24 hours', 'Higher tiers that grow automatically with good quality, up to unlimited'],
  ['Phone numbers', 'A small number', 'More numbers per business'],
  ['Verified business badge', 'Not eligible', 'Eligible to apply'],
  ['What Meta asks for', 'Nothing extra', 'Business documents such as GST certificate, Udyam or incorporation certificate'],
]

export function GettingConnected() {
  return (
    <section id="requirements" className="border-t border-line py-20 md:py-28">
      <Container>
        <SectionHeader
          index="04"
          eyebrow="Getting connected"
          title="What you need before you connect."
          description="Most businesses finish setup in one sitting. These are Meta’s requirements, laid out plainly so there are no surprises halfway through."
        />

        <div className="mt-14 grid gap-5 md:grid-cols-2">
          {cards.map((card, i) => (
            <Reveal as="article" key={card.title} delay={(i % 2) * 100} className="flex">
              <TiltCard max={3} className="w-full rounded-xl border border-line bg-card p-6 md:p-7">
                <h3 className="text-[18px] font-semibold tracking-[-0.01em]">{card.title}</h3>
                <ul className="mt-4 space-y-2.5 text-[15px] leading-relaxed text-muted">
                  {card.points.map((point) => (
                    <li key={point} className="flex gap-2.5">
                      <Check className="mt-1 size-4 shrink-0 text-accent-2" aria-hidden="true" />
                      <span>{point}</span>
                    </li>
                  ))}
                </ul>
              </TiltCard>
            </Reveal>
          ))}
        </div>

        <Reveal className="mt-16 grid grid-cols-1 gap-10 lg:grid-cols-12">
          <div className="lg:col-span-4">
            <h3 className="font-display text-[1.6rem] font-semibold leading-[1.1] tracking-[-0.025em]">
              Do you need Meta business verification?
            </h3>
            <p className="mt-4 text-[15.5px] leading-relaxed text-muted">
              Not to get started. You can connect and send right away. Verification unlocks higher sending limits and
              is worth doing once you plan to message your full customer list — {site.name} helps you prepare the
              documents.
            </p>
          </div>
          <div className="min-w-0 lg:col-span-8">
            <dl className="divide-y divide-line border-y border-ink md:hidden">
              {limits.map(([capability, unverified, verified]) => (
                <div key={capability} className="py-4">
                  <dt className="text-[15px] font-semibold">{capability}</dt>
                  <dd className="mt-2 grid grid-cols-2 gap-4 text-[14px]">
                    <span className="text-muted">
                      <span className="block font-mono text-[10.5px] uppercase tracking-[0.1em]">Unverified</span>
                      {unverified}
                    </span>
                    <span>
                      <span className="block font-mono text-[10.5px] uppercase tracking-[0.1em] text-accent-2">
                        Verified
                      </span>
                      {verified}
                    </span>
                  </dd>
                </div>
              ))}
            </dl>

            <div className="hidden overflow-x-auto md:block">
            <table className="w-full min-w-[560px] border-collapse text-left text-[14.5px]">
              <caption className="sr-only">Unverified versus verified business on WhatsApp</caption>
              <thead>
                <tr className="border-b border-ink">
                  <th scope="col" className="w-[34%] py-3 pr-4 font-mono text-[11px] font-normal uppercase tracking-[0.12em] text-muted">
                    Capability
                  </th>
                  <th scope="col" className="py-3 pr-4 font-semibold">
                    Without verification
                  </th>
                  <th scope="col" className="py-3 font-semibold">
                    With verification
                  </th>
                </tr>
              </thead>
              <tbody>
                {limits.map(([capability, unverified, verified]) => (
                  <tr key={capability} className="border-b border-line align-top">
                    <th scope="row" className="py-3.5 pr-4 font-medium">
                      {capability}
                    </th>
                    <td className="py-3.5 pr-4 text-muted">{unverified}</td>
                    <td className="py-3.5">{verified}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
            <p className="mt-4 text-[13px] text-muted">
              Messaging limits are set by Meta and change from time to time. Your current limit is always shown in your
              dashboard.
            </p>
          </div>
        </Reveal>
      </Container>
    </section>
  )
}
