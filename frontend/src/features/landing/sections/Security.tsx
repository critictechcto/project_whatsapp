import { useEffect, useRef, useState } from 'react'
import { Check, FileText, KeyRound, Lock, ShieldCheck, UserCog, Users } from 'lucide-react'
import { Container } from '../../../components/ui/Container'
import { Reveal } from '../../../components/ui/Reveal'
import { SectionHeader } from '../../../components/ui/SectionHeader'
import { site } from '../../../config/site'
import { usePrefersReducedMotion } from '../../../lib/motion'
import { useOnScreen } from '../lib/useOnScreen'
import './Security.css'

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

// Illustrative values only: a Meta-style access token and a Fernet-style ciphertext of the same length.
const PLAIN_TOKEN = 'EAAGm0PZCx7sBAO9kqLz'
const CIPHER_TOKEN = 'gAAAAABmQ3r9Xk2vT0aZ'
const SCRAMBLE_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'

type Phase = 'plain' | 'encrypting' | 'sealed'

const PHASE_MS: Record<Phase, number> = { plain: 1600, encrypting: 1000, sealed: 3200 }
const SCRAMBLE_STEP_MS = 60

const statusLabel: Record<Phase, string> = {
  plain: 'Access token from Meta',
  encrypting: 'Encrypting…',
  sealed: 'Stored encrypted',
}

/** Characters settle from left to right into the ciphertext while the rest flicker. */
function scramble(progress: number) {
  const settled = Math.floor(progress * CIPHER_TOKEN.length)
  let text = CIPHER_TOKEN.slice(0, settled)
  for (let i = settled; i < CIPHER_TOKEN.length; i++) {
    text += SCRAMBLE_CHARS[Math.floor(Math.random() * SCRAMBLE_CHARS.length)]
  }
  return text
}

/**
 * Decorative loop: an access token is encrypted and dropped into a stack of stored secrets.
 * Plays only while on screen; reduced motion shows the sealed state without moving.
 */
function TokenVault() {
  const stageRef = useRef<HTMLDivElement | null>(null)
  const onScreen = useOnScreen(stageRef)
  const reducedMotion = usePrefersReducedMotion()
  const [loopPhase, setPhase] = useState<Phase>('plain')
  const [loopText, setText] = useState(PLAIN_TOKEN)
  const phase = reducedMotion ? 'sealed' : loopPhase
  const text = reducedMotion ? CIPHER_TOKEN : loopText
  // Remounts the token card each loop so it fades in at the top instead of flying back up.
  const [cycle, setCycle] = useState(0)

  useEffect(() => {
    if (reducedMotion || !onScreen) return

    if (phase === 'encrypting') {
      const startedAt = Date.now()
      const interval = window.setInterval(() => {
        setText(scramble(Math.min((Date.now() - startedAt) / PHASE_MS.encrypting, 1)))
      }, SCRAMBLE_STEP_MS)
      const timer = window.setTimeout(() => {
        setText(CIPHER_TOKEN)
        setPhase('sealed')
      }, PHASE_MS.encrypting)
      return () => {
        window.clearInterval(interval)
        window.clearTimeout(timer)
      }
    }

    const timer = window.setTimeout(() => {
      if (phase === 'plain') {
        setPhase('encrypting')
      } else {
        setText(PLAIN_TOKEN)
        setPhase('plain')
        setCycle((current) => current + 1)
      }
    }, PHASE_MS[phase])
    return () => window.clearTimeout(timer)
  }, [phase, onScreen, reducedMotion])

  return (
    <div ref={stageRef} aria-hidden="true" data-phase={phase} className="vault-stage select-none">
      <div className="vault-scene">
        <div className="vault-layer" data-depth="2" />
        <div className="vault-layer" data-depth="1" />
        <div className="vault-card">
          <div className="flex items-center justify-between border-b border-line-2 px-4 py-3">
            <span className="flex items-center gap-2 text-[13px] font-semibold">
              <Lock className="size-3.5 text-accent-2" />
              Encrypted at rest
            </span>
            <span className="font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted">Your workspace</span>
          </div>
          <p className="px-4 pt-3 text-[12.5px] leading-snug text-muted">
            Decrypted only by our servers to send and receive your messages.
          </p>
          <div className="vault-slot" />
        </div>
        <div key={cycle} className="vault-token flex items-center gap-3 px-3.5">
          <span className="grid size-8 shrink-0 place-items-center rounded-md bg-accent-soft text-accent-2">
            {phase === 'sealed' ? <Check className="size-4" /> : <KeyRound className="size-4" />}
          </span>
          <span className="min-w-0">
            <span className="vault-status block text-[11.5px] font-medium text-muted">{statusLabel[phase]}</span>
            <span className="block truncate font-mono text-[13px] tracking-[0.02em] text-ink">{text}…</span>
          </span>
        </div>
      </div>
    </div>
  )
}

export function Security() {
  return (
    <section id="security" className="py-20 md:py-28">
      <Container>
        <div className="grid items-end gap-10 lg:grid-cols-12">
          <SectionHeader
            index="11"
            eyebrow="Security & data"
            title="Your customers’ data, handled with care."
            description="WhatsApp conversations are personal. We treat access to them that way."
            className="lg:col-span-7"
          />
          <Reveal delay={120} className="lg:col-span-5">
            <TokenVault />
          </Reveal>
        </div>
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
