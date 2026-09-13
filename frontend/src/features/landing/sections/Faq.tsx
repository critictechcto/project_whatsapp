import { Accordion, type AccordionItem } from '../../../components/ui/Accordion'
import { Container } from '../../../components/ui/Container'
import { Reveal } from '../../../components/ui/Reveal'
import { SectionHeader } from '../../../components/ui/SectionHeader'
import { site } from '../../../config/site'

const faqs: AccordionItem[] = [
  {
    question: 'Do I need a new phone number?',
    answer:
      'No. Any number your business owns that can receive an SMS or voice call works, including landlines. The only rule is that it can’t be active on WhatsApp at the same time — unless you connect a WhatsApp Business app number using coexistence.',
  },
  {
    question: 'Can I keep using the WhatsApp Business app on my phone?',
    answer:
      'In many cases, yes. Meta’s coexistence feature lets a WhatsApp Business app number stay on the app while also being connected to us, with recent chat history synced. It works with the WhatsApp Business app only, not personal WhatsApp, and availability depends on Meta.',
  },
  {
    question: 'Does my business need to be verified by Meta?',
    answer:
      'Not to start. Unverified businesses can message up to 250 unique customers per day with business-initiated messages, and reply to anyone who messages them. Verifying with documents like a GST certificate unlocks higher limits and more numbers.',
  },
  {
    question: 'What will I pay in total?',
    answer: `Your ${site.name} plan, plus Meta’s charges for template messages, which depend on the category (marketing, utility or authentication). Meta’s charges are passed on at cost, and replies inside the 24-hour window are free under Meta’s current pricing. Plan prices exclude ${site.gstRate}% GST.`,
  },
  {
    question: 'Will my number get banned?',
    answer:
      'Using the official API is fully allowed, so the risk that comes with QR-code tools doesn’t apply. What can still hurt a number is messaging people who didn’t opt in, which leads to blocks and reports. We require opt-in records, process STOP requests automatically and show your quality rating so you can act early.',
  },
  {
    question: 'How long does template approval take?',
    answer:
      'Meta reviews templates automatically. Most are approved within minutes; some take up to 24 hours. If one is rejected, we show Meta’s reason so you can edit and resubmit.',
  },
  {
    question: 'Can I message my whole customer list at once?',
    answer:
      'Yes — everyone on it who has opted in, within your current Meta messaging limit. Large campaigns are queued and paced automatically, and you see a cost estimate before sending.',
  },
  {
    question: 'Can several team members reply from one number?',
    answer:
      'Yes. Every plan includes a shared inbox with conversation assignment, internal notes and roles, so your whole team can work from the same WhatsApp number.',
  },
  {
    question: 'Do you have an API?',
    answer:
      'Yes, on Growth and Pro. Use our REST API to send messages and manage contacts, and receive signed webhooks for delivery, read, failure and reply events.',
  },
  {
    question: 'Can I cancel anytime?',
    answer:
      'Yes. There’s no lock-in on monthly plans, and annual plans simply don’t renew. Because your WhatsApp Business Account belongs to you, you keep your number, templates and verification if you leave.',
  },
]

export function Faq() {
  return (
    <section id="faq" className="border-t border-line py-20 md:py-28">
      <Container className="grid gap-12 lg:grid-cols-12 lg:gap-10">
        <div className="lg:col-span-4">
          <SectionHeader index="10" eyebrow="FAQ" title="Questions we hear every week." />
          <p className="mt-6 text-[15.5px] leading-relaxed text-muted">
            Something not covered here? Email{' '}
            <a href={`mailto:${site.email.sales}`} className="text-ink underline decoration-line underline-offset-4 hover:decoration-ink">
              {site.email.sales}
            </a>{' '}
            and a real person will reply within one working day.
          </p>
        </div>
        <Reveal delay={120} className="lg:col-span-8">
          <Accordion items={faqs} />
        </Reveal>
      </Container>
    </section>
  )
}
