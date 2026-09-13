import { ArrowRight, CalendarClock, Moon, Repeat, Users } from 'lucide-react'
import { Badge } from '../../../components/ui/Badge'
import { ChatBubble } from './ChatBubble'
import { Window } from './Window'

export function ScheduleMockup() {
  const rows = [
    { icon: CalendarClock, label: 'Send on', value: '20 Sep 2026, 10:00 AM IST' },
    { icon: Repeat, label: 'Repeat', value: 'Monthly, on the 20th' },
    { icon: Users, label: 'Audience', value: 'Class 7 parents · 842 contacts' },
    { icon: Moon, label: 'Quiet hours', value: 'No sends 9:00 PM – 9:00 AM' },
  ]
  const upcoming = [
    ['20 Sep', 'Term fee reminder', 'Scheduled'],
    ['20 Oct', 'Term fee reminder', 'Scheduled'],
    ['20 Nov', 'Term fee reminder', 'Scheduled'],
  ]

  return (
    <Window title="Schedule · Fee reminder">
      <dl className="divide-y divide-line-2">
        {rows.map(({ icon: Icon, label, value }) => (
          <div key={label} className="flex items-center gap-3 px-4 py-3">
            <Icon className="size-4 shrink-0 text-muted" />
            <dt className="w-24 shrink-0 text-[12px] text-muted">{label}</dt>
            <dd className="min-w-0 truncate text-[12.5px] font-medium">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="border-t border-line bg-paper/60 px-4 py-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">Upcoming runs</p>
        <ul className="mt-2 space-y-1.5">
          {upcoming.map(([date, name, status]) => (
            <li key={date} className="flex items-center gap-3 text-[12px]">
              <span className="w-12 font-mono text-muted">{date}</span>
              <span className="flex-1 truncate">{name}</span>
              <Badge>{status}</Badge>
            </li>
          ))}
        </ul>
      </div>
    </Window>
  )
}

export function AutomationMockup() {
  const rules = [
    { trigger: 'Keyword: “timings”, “open”', action: 'Reply with store hours' },
    { trigger: 'Keyword: “STOP”', action: 'Opt out contact + confirm' },
    { trigger: 'Outside business hours', action: 'Away message, assign next morning' },
  ]

  return (
    <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)]">
      <Window title="Automations · 3 active">
        <ul className="divide-y divide-line-2">
          {rules.map((rule) => (
            <li key={rule.trigger} className="px-4 py-3">
              <p className="text-[12px] text-muted">{rule.trigger}</p>
              <p className="mt-1 flex items-center gap-1.5 text-[12.5px] font-medium">
                <ArrowRight className="size-3.5 text-accent-2" />
                {rule.action}
              </p>
            </li>
          ))}
        </ul>
      </Window>
      <div aria-hidden="true" className="space-y-2.5 rounded-xl border border-line bg-wallpaper p-3">
        <ChatBubble from="customer" time="21:14">
          Hi, what are your timings?
        </ChatBubble>
        <ChatBubble from="business" label="Auto-reply" time="21:14">
          We’re open 10 AM – 8 PM, Monday to Saturday. Reply 1 for store location or 2 to talk to our team.
        </ChatBubble>
        <ChatBubble from="customer" time="21:15">
          2
        </ChatBubble>
        <ChatBubble from="business" label="Auto-reply" time="21:15">
          Thanks! Our team will reply first thing tomorrow morning.
        </ChatBubble>
      </div>
    </div>
  )
}

export function ContactsMockup() {
  const contacts = [
    { name: 'Priya Sharma', phone: '+91 98XXX 22031', tag: 'Repeat buyer', source: 'Checkout', subscribed: true },
    { name: 'Rahul Verma', phone: '+91 99XXX 80412', tag: 'B2B', source: 'Website form', subscribed: true },
    { name: 'Kavya Iyer', phone: '+91 97XXX 11598', tag: 'New', source: 'Click-to-chat ad', subscribed: true },
    { name: 'Imran Qureshi', phone: '+91 90XXX 67320', tag: 'Repeat buyer', source: 'In-store', subscribed: false },
    { name: 'Meera Nair', phone: '+91 81XXX 40077', tag: 'New', source: 'CSV import', subscribed: true },
  ]

  return (
    <Window title="Contacts · 4,812">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-left text-[12px]">
          <thead>
            <tr className="border-b border-line-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
              <th className="px-4 py-2 font-normal">Name</th>
              <th className="px-2 py-2 font-normal">Tag</th>
              <th className="px-2 py-2 font-normal">Opt-in source</th>
              <th className="px-4 py-2 font-normal">Status</th>
            </tr>
          </thead>
          <tbody>
            {contacts.map((c) => (
              <tr key={c.name} className="border-b border-line-2 last:border-b-0">
                <td className="px-4 py-2.5">
                  <p className="font-medium">{c.name}</p>
                  <p className="font-mono text-[10.5px] text-muted">{c.phone}</p>
                </td>
                <td className="px-2 py-2.5 text-muted">{c.tag}</td>
                <td className="px-2 py-2.5 text-muted">{c.source}</td>
                <td className="px-4 py-2.5">
                  {c.subscribed ? <Badge tone="green">Subscribed</Badge> : <Badge tone="red">Opted out</Badge>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Window>
  )
}

export function AnalyticsMockup() {
  const funnel = [
    { label: 'Sent', value: 100, count: '12,480' },
    { label: 'Delivered', value: 97, count: '12,103' },
    { label: 'Read', value: 74, count: '9,215' },
    { label: 'Replied', value: 8, count: '1,042' },
  ]
  const failures = [
    ['Not a WhatsApp user', '214'],
    ['Messaging limit reached', '98'],
    ['Number opted out', '65'],
  ]

  return (
    <Window title="Report · Festive sale — early access">
      <div className="space-y-3 px-4 py-4">
        {funnel.map((row, i) => (
          <div key={row.label} className="grid grid-cols-[72px_minmax(0,1fr)_64px] items-center gap-3 text-[12px]">
            <span className="text-muted">{row.label}</span>
            <div className="h-5 overflow-hidden rounded-sm bg-line-2">
              <div
                className="grow-x h-full rounded-sm bg-accent"
                style={{ width: `${row.value}%`, animationDelay: `${i * 120}ms` }}
              />
            </div>
            <span className="text-right font-mono">{row.count}</span>
          </div>
        ))}
      </div>
      <div className="border-t border-line bg-paper/60 px-4 py-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">Why 377 messages failed</p>
        <ul className="mt-2 space-y-1.5 text-[12px]">
          {failures.map(([reason, count]) => (
            <li key={reason} className="flex justify-between gap-3">
              <span>{reason}</span>
              <span className="font-mono text-muted">{count}</span>
            </li>
          ))}
        </ul>
      </div>
    </Window>
  )
}

export function TeamMockup() {
  const numbers = [
    { number: '+91 98XXX 41207', label: 'Sales', quality: 'High', tone: 'green' as const },
    { number: '+91 80XXX 55120', label: 'Support', quality: 'Medium', tone: 'amber' as const },
  ]
  const members = [
    { name: 'Neha Kapoor', role: 'Admin', access: 'All numbers' },
    { name: 'Rohit Das', role: 'Agent', access: 'Support only' },
    { name: 'Farah Khan', role: 'Viewer', access: 'Reports only' },
  ]

  return (
    <Window title="Settings · Numbers & team">
      <div className="px-4 py-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">WhatsApp numbers</p>
        <ul className="mt-2 space-y-2">
          {numbers.map((n) => (
            <li key={n.number} className="flex items-center justify-between gap-3 rounded-md border border-line-2 px-3 py-2">
              <div className="min-w-0">
                <p className="font-mono text-[12px]">{n.number}</p>
                <p className="text-[11px] text-muted">{n.label}</p>
              </div>
              <Badge tone={n.tone}>Quality: {n.quality}</Badge>
            </li>
          ))}
        </ul>
      </div>
      <div className="border-t border-line-2 px-4 py-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">Team</p>
        <ul className="mt-2 divide-y divide-line-2">
          {members.map((m) => (
            <li key={m.name} className="flex items-center gap-3 py-2 text-[12px]">
              <span className="grid size-7 shrink-0 place-items-center rounded-full bg-paper-2 text-[10.5px] font-semibold">
                {m.name
                  .split(' ')
                  .map((part) => part[0])
                  .join('')}
              </span>
              <span className="flex-1 truncate font-medium">{m.name}</span>
              <span className="hidden text-muted sm:block">{m.access}</span>
              <Badge tone={m.role === 'Admin' ? 'ink' : 'neutral'}>{m.role}</Badge>
            </li>
          ))}
        </ul>
      </div>
    </Window>
  )
}
