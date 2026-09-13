import { Check, X } from 'lucide-react'
import { Container } from '../../../components/ui/Container'
import { Reveal } from '../../../components/ui/Reveal'
import { SectionHeader } from '../../../components/ui/SectionHeader'
import { site } from '../../../config/site'

const rows: Array<[string, string, string]> = [
  ['Allowed by WhatsApp', 'Yes — Meta’s official Business Platform', 'No — violates WhatsApp’s Terms of Service'],
  ['Risk of number ban', 'Low, when you message opted-in contacts', 'High, often soon after bulk sending starts'],
  ['Phone must stay online', 'No — runs entirely in the cloud', 'Yes — a phone or browser session must stay connected'],
  ['Templates & buttons', 'Approved templates, quick replies, call-to-action buttons', 'Plain text that imitates a person typing'],
  ['Delivery & read status', 'Real-time events from Meta', 'Guessed from the web interface, often wrong'],
  ['Verified business badge', 'Eligible to apply', 'Not possible'],
  ['What it really costs', 'Plan price + Meta’s published per-message fees', 'Looks cheap — until the number is lost'],
]

export function OfficialVsUnofficial() {
  return (
    <section id="why-official" className="py-20 md:py-28">
      <Container className="grid gap-12 lg:grid-cols-12 lg:gap-10">
        <SectionHeader
          className="lg:col-span-5"
          index="01"
          eyebrow="Why official"
          title="Cheap QR-code tools cost you your number."
          description={
            <>
              Many “bulk WhatsApp” tools work by scanning a QR code and automating WhatsApp Web. That breaks
              WhatsApp’s terms, and numbers used this way get banned — along with every customer conversation on them.{' '}
              {site.name} only uses Meta’s official Cloud API.
            </>
          }
        />

        <Reveal delay={120} className="min-w-0 lg:col-span-7 lg:pt-12">
          {/* Phones: one stacked card per row instead of a sideways-scrolling table */}
          <dl className="divide-y divide-line border-y border-ink md:hidden">
            {rows.map(([topic, official, unofficial]) => (
              <div key={topic} className="py-4">
                <dt className="text-[15px] font-semibold">{topic}</dt>
                <dd className="mt-2 flex gap-2 text-[14.5px]">
                  <Check className="mt-0.5 size-4 shrink-0 text-accent-2" aria-hidden="true" />
                  <span>
                    <span className="sr-only">{site.name}: </span>
                    {official}
                  </span>
                </dd>
                <dd className="mt-1.5 flex gap-2 text-[14.5px] text-muted">
                  <X className="mt-0.5 size-4 shrink-0 text-signal" aria-hidden="true" />
                  <span>
                    <span className="sr-only">QR-code tools: </span>
                    {unofficial}
                  </span>
                </dd>
              </div>
            ))}
          </dl>

          <div className="hidden overflow-x-auto md:block">
          <table className="w-full min-w-[600px] border-collapse text-left text-[14.5px]">
            <caption className="sr-only">
              Comparison of {site.name} on the official API with unofficial QR-code tools
            </caption>
            <thead>
              <tr className="border-b border-ink">
                <th scope="col" className="w-[28%] py-3 pr-4 font-mono text-[11px] font-normal uppercase tracking-[0.12em] text-muted">
                  What matters
                </th>
                <th scope="col" className="py-3 pr-4 font-semibold">
                  {site.name} · Official API
                </th>
                <th scope="col" className="py-3 font-semibold text-muted">
                  QR-code tools
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([topic, official, unofficial]) => (
                <tr key={topic} className="border-b border-line align-top transition-colors hover:bg-card/70">
                  <th scope="row" className="py-4 pr-4 font-medium">
                    {topic}
                  </th>
                  <td className="py-4 pr-4">
                    <span className="flex gap-2">
                      <Check className="mt-0.5 size-4 shrink-0 text-accent-2" aria-hidden="true" />
                      {official}
                    </span>
                  </td>
                  <td className="py-4 text-muted">
                    <span className="flex gap-2">
                      <X className="mt-0.5 size-4 shrink-0 text-signal" aria-hidden="true" />
                      {unofficial}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </Reveal>
      </Container>
    </section>
  )
}
