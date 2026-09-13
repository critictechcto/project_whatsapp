import { useState } from 'react'
import { Check } from 'lucide-react'
import { Container } from '../../../components/ui/Container'
import { Reveal } from '../../../components/ui/Reveal'
import { SectionHeader } from '../../../components/ui/SectionHeader'
import { site } from '../../../config/site'
import { cn } from '../../../lib/cn'

const apiHost = `api.${site.domain}`

const snippets = {
  request: {
    label: 'Send a message',
    code: `curl -X POST https://${apiHost}/v1/messages \\
  -H "Authorization: Bearer pw_live_••••••••••••" \\
  -H "Idempotency-Key: order-20418-shipped" \\
  -H "Content-Type: application/json" \\
  -d '{
    "from": "+919800041207",
    "to": "+919800022031",
    "template": {
      "name": "order_shipped",
      "language": "en",
      "variables": ["Priya", "#SR-20418", "Thursday"]
    }
  }'`,
  },
  webhook: {
    label: 'Webhook event',
    code: `POST https://your-app.example/webhooks/whatsapp
X-Signature: sha256=9f2c41e0b7…

{
  "event": "message.read",
  "message_id": "msg_01J8Z6V4K2QX",
  "to": "+919800022031",
  "template": "order_shipped",
  "occurred_at": "2026-09-18T10:42:07+05:30"
}`,
  },
}

const points = [
  'Send template and free-form messages with one endpoint',
  'Create contacts, manage opt-in and tags from your system',
  'Signed webhooks for delivered, read, failed and replied events',
  'Idempotency keys so retries never send twice',
  'Separate test and live API keys per workspace',
]

export function Developers() {
  const [active, setActive] = useState<keyof typeof snippets>('request')

  return (
    <section id="developers" className="bg-ink py-20 text-paper md:py-28">
      <Container className="grid gap-12 lg:grid-cols-12 lg:gap-10">
        <div className="lg:col-span-5">
          <SectionHeader
            inverse
            index="08"
            eyebrow="Developers"
            title="A clean API on top of Meta’s."
            description="Trigger messages from your store, CRM or billing system. We handle Meta’s tokens, template formats, retries and rate limits, so your code stays short."
          />
          <ul className="mt-8 space-y-3 text-[15px] text-paper/85">
            {points.map((point) => (
              <li key={point} className="flex gap-2.5">
                <Check className="mt-0.5 size-4 shrink-0 text-[#8fd0ab]" aria-hidden="true" />
                {point}
              </li>
            ))}
          </ul>
          <p className="mt-8 text-[14px] text-paper/60">API access is included on Growth and Pro plans.</p>
        </div>

        <Reveal delay={120} className="min-w-0 lg:col-span-7 lg:pt-10">
          <div className="overflow-hidden rounded-xl border border-paper/15 bg-[#0a1d17]">
            <div className="flex items-center gap-1 border-b border-paper/10 px-3 py-2">
              {(Object.keys(snippets) as Array<keyof typeof snippets>).map((key) => (
                <button
                  key={key}
                  type="button"
                  aria-pressed={active === key}
                  onClick={() => setActive(key)}
                  className={cn(
                    'rounded-md px-3 py-1.5 font-mono text-[12px] transition-colors',
                    active === key ? 'bg-paper/10 text-paper' : 'text-paper/60 hover:text-paper',
                  )}
                >
                  {snippets[key].label}
                </button>
              ))}
            </div>
            <pre
              key={active}
              className="fade-up overflow-x-auto p-5 font-mono text-[12.5px] leading-[1.7] text-paper/85"
            >
              <code>{snippets[active].code}</code>
            </pre>
          </div>
        </Reveal>
      </Container>
    </section>
  )
}
