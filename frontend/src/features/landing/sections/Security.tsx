import { FileText, KeyRound, Lock, ShieldCheck, UserCog, Users } from 'lucide-react'
import { Container } from '../../../components/ui/Container'
import { Reveal } from '../../../components/ui/Reveal'
import { SectionHeader } from '../../../components/ui/SectionHeader'
import { site } from '../../../config/site'

const items = [
  {
    icon: ShieldCheck,
    title: 'You own your WhatsApp account',
    body: `Your WhatsApp Business Account, number, templates and verification belong to your business in Meta — not to ${site.name}. Disconnect us any time and keep everything.`,
  },
  {
    icon: KeyRound,
    title: 'Encrypted access tokens',
    body: 'The token Meta issues for your account is encrypted at rest and only used by our servers to send and receive your messages.',
  },
  {
    icon: Lock,
    title: 'Verified webhooks',
    body: 'Every event from Meta is checked against its signature before we process it, and all traffic runs over HTTPS.',
  },
  {
    icon: UserCog,
    title: 'Role-based access',
    body: 'Admins, agents and viewers see only what they need. Agents can be limited to specific numbers.',
  },
  {
    icon: Users,
    title: 'Consent records',
    body: 'Opt-in source and time are stored for each contact, supporting your obligations under India’s Digital Personal Data Protection Act, 2023.',
  },
  {
    icon: FileText,
    title: 'Export and deletion',
    body: 'Export your contacts and message history whenever you like, and ask us to delete your workspace data when you leave.',
  },
]

export function Security() {
  return (
    <section id="security" className="py-20 md:py-28">
      <Container>
        <SectionHeader
          index="10"
          eyebrow="Security & data"
          title="Your customers’ data, handled with care."
          description="WhatsApp conversations are personal. We treat access to them that way."
        />
        <Reveal
          as="ul"
          className="mt-14 grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-2 lg:grid-cols-3"
        >
          {items.map(({ icon: Icon, title, body }) => (
            <li key={title} className="group/item bg-card p-6 transition-colors duration-300 hover:bg-white md:p-7">
              <Icon
                className="size-5 text-accent-2 transition-transform duration-300 ease-soft group-hover/item:-translate-y-0.5"
                aria-hidden="true"
              />
              <h3 className="mt-5 text-[16.5px] font-semibold tracking-[-0.01em]">{title}</h3>
              <p className="mt-2 text-[14.5px] leading-relaxed text-muted">{body}</p>
            </li>
          ))}
        </Reveal>
      </Container>
    </section>
  )
}
