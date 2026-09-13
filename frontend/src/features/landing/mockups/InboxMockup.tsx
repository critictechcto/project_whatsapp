import { useEffect, useState } from 'react'
import { Clock, Send } from 'lucide-react'
import { cn } from '../../../lib/cn'
import { prefersReducedMotion } from '../../../lib/motion'
import { ChatBubble, TypingBubble } from './ChatBubble'
import { Window } from './Window'

const conversations = [
  { name: 'Priya Sharma', preview: 'Is COD available for Jaipur?', time: '10:42', unread: 2, active: true },
  { name: 'Rahul Verma', preview: 'Thanks, got the invoice', time: '10:31' },
  { name: 'Sunrise Dental', preview: 'Confirm', time: '10:18' },
  { name: 'Kavya Iyer', preview: 'Can I change the size to M?', time: '09:57', unread: 1 },
  { name: 'Arjun Mehta', preview: 'Paid via UPI just now', time: '09:40' },
]

// When `animated`, the chat plays out: template → customer question → agent typing → reply.
const STEP_DELAYS_MS = [500, 1400, 2300, 3700]
const FINAL_STEP = STEP_DELAYS_MS.length

export function InboxMockup({ className, animated = false }: { className?: string; animated?: boolean }) {
  const [step, setStep] = useState(animated ? 0 : FINAL_STEP)

  useEffect(() => {
    if (!animated) return
    if (prefersReducedMotion()) {
      setStep(FINAL_STEP)
      return
    }
    const timers = STEP_DELAYS_MS.map((delay, i) => window.setTimeout(() => setStep(i + 1), delay))
    return () => timers.forEach((timer) => window.clearTimeout(timer))
  }, [animated])

  const pop = animated ? 'chat-pop' : undefined

  return (
    <Window
      title="Inbox · +91 98XXX 41207"
      className={className}
      right={
        <span className="flex items-center gap-1.5 font-mono text-[10px] text-accent-2">
          <span className="relative flex size-1.5">
            <span className="pulse-ring absolute inset-0 rounded-full bg-accent" />
            <span className="relative size-1.5 rounded-full bg-accent" />
          </span>
          Connected
        </span>
      }
    >
      <div className="grid grid-cols-1 sm:grid-cols-[200px_minmax(0,1fr)]">
        <aside className="hidden border-r border-line-2 sm:block">
          <div className="flex gap-1 border-b border-line-2 px-3 py-2.5 text-[11px]">
            <span className="rounded bg-ink px-2 py-0.5 text-paper">Open 12</span>
            <span className="px-2 py-0.5 text-muted">Mine 4</span>
            <span className="px-2 py-0.5 text-muted">Closed</span>
          </div>
          <ul>
            {conversations.map((c) => (
              <li key={c.name} className={cn('border-b border-line-2 px-3 py-2.5', c.active && 'bg-accent-soft/70')}>
                <div className="flex items-baseline justify-between gap-2">
                  <p className="truncate text-[12px] font-medium">{c.name}</p>
                  <span className="font-mono text-[10px] text-muted">{c.time}</span>
                </div>
                <div className="mt-0.5 flex items-center justify-between gap-2">
                  <p className="truncate text-[11.5px] text-muted">{c.preview}</p>
                  {c.unread && (
                    <span className="grid size-4 shrink-0 place-items-center rounded-full bg-accent text-[9px] font-semibold text-white">
                      {c.unread}
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </aside>

        <section className="flex min-w-0 flex-col">
          <header className="flex items-center justify-between gap-3 border-b border-line-2 px-4 py-2.5">
            <div className="min-w-0">
              <p className="text-[13px] font-medium">Priya Sharma</p>
              <p className="truncate font-mono text-[10px] text-muted">+91 98XXX 22031 · Opted in at checkout</p>
            </div>
            <span className="shrink-0 rounded border border-line bg-card px-2 py-1 text-[10.5px] text-muted">
              Assigned: Neha
            </span>
          </header>

          <div className="flex min-h-[290px] flex-1 flex-col justify-end gap-2.5 bg-wallpaper px-4 py-4">
            {step >= 1 && (
              <ChatBubble
                className={pop}
                from="business"
                label="Utility template"
                time="Yesterday 18:05"
                buttons={['Track order']}
              >
                Hi Priya, your order #RB-20418 has been shipped. Expected delivery: Thursday.
              </ChatBubble>
            )}
            {step >= 2 && (
              <ChatBubble className={pop} from="customer" time="10:41">
                Hi! Is COD available for Jaipur? I want to order one more.
              </ChatBubble>
            )}
            {step === 3 && <TypingBubble className={pop} />}
            {step >= 4 && (
              <ChatBubble className={pop} from="business" time="10:42">
                Yes, Cash on Delivery is available across Jaipur. Sharing the product link now.
              </ChatBubble>
            )}
          </div>

          <div className="flex items-center gap-2 border-t border-line-2 px-3 py-2.5">
            <span className="hidden items-center gap-1.5 rounded bg-accent-soft px-2 py-1 font-mono text-[10px] text-accent-2 min-[420px]:flex">
              <Clock className="size-3" />
              Window open · 23h 17m
            </span>
            <div className="h-8 min-w-0 flex-1 truncate rounded-md border border-line bg-white px-3 text-[12px] leading-8 text-muted">
              Type a reply…
            </div>
            <span className="grid size-8 shrink-0 place-items-center rounded-md bg-ink text-paper">
              <Send className="size-3.5" />
            </span>
          </div>
        </section>
      </div>
    </Window>
  )
}
