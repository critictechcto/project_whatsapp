import type { ReactNode } from 'react'
import { Check } from 'lucide-react'
import { Container } from '../../../components/ui/Container'
import { ScrollDepth } from '../../../components/ui/ScrollDepth'
import { SectionHeader } from '../../../components/ui/SectionHeader'
import { Tabs, type TabItem } from '../../../components/ui/Tabs'
import { CampaignMockup } from '../mockups/CampaignMockup'
import {
  AnalyticsMockup,
  AutomationMockup,
  ContactsMockup,
  ScheduleMockup,
  TeamMockup,
} from '../mockups/FeatureMockups'
import { InboxMockup } from '../mockups/InboxMockup'
import { TemplateStack } from '../mockups/TemplateStack'

type Feature = {
  id: string
  label: string
  title: string
  body: string
  points: string[]
  mockup: ReactNode
}

const features: Feature[] = [
  {
    id: 'campaigns',
    label: 'Bulk campaigns',
    title: 'Send to thousands without losing the personal touch.',
    body: 'Pick an approved template, choose an audience by tag or list, and fill variables like name, order number or due date from your contact data.',
    points: [
      'Personalised variables, images, documents and buttons',
      'Sending is paced to stay inside your Meta messaging limit',
      'Estimate of Meta’s charges shown before you confirm',
      'Opted-out contacts are skipped automatically',
    ],
    mockup: <CampaignMockup className="mx-auto max-w-md" />,
  },
  {
    id: 'scheduling',
    label: 'Scheduled messages',
    title: 'Reminders that go out on time, every time.',
    body: 'Schedule a one-off send or set a recurring rule for fee reminders, renewals and appointment follow-ups. All times are in IST.',
    points: [
      'One-time, daily, weekly or monthly schedules',
      'Quiet hours so customers aren’t messaged at night',
      'Pause or edit any upcoming run',
      'Trigger sends from your own system through the API',
    ],
    mockup: <ScheduleMockup />,
  },
  {
    id: 'templates',
    label: 'Template manager',
    title: 'Create templates and track Meta’s approval in one place.',
    body: 'Business-initiated messages must use a template approved by Meta. Write it once with variables and buttons, submit it, and watch its status update automatically.',
    points: [
      'Marketing, utility and authentication categories',
      'English, Hindi and other supported languages',
      'Live preview exactly as the customer will see it',
      'Rejection reasons from Meta, so you can fix and resubmit',
    ],
    mockup: <TemplateStack />,
  },
  {
    id: 'inbox',
    label: 'Team inbox',
    title: 'One number, the whole team replying.',
    body: 'Every customer reply lands in a shared inbox. Assign conversations, leave internal notes and see exactly how long the 24-hour reply window has left.',
    points: [
      'Assign to teammates or auto-distribute',
      'Internal notes customers never see',
      'Saved replies for common questions',
      'Send images, PDFs and voice notes',
    ],
    mockup: <InboxMockup />,
  },
  {
    id: 'automations',
    label: 'Auto-replies',
    title: 'Answer the common questions automatically.',
    body: 'Set keyword replies, away messages and simple menus so customers get an instant answer — and a person steps in only when it’s needed.',
    points: [
      'Keyword and button-based replies',
      'Away messages outside business hours',
      'STOP and opt-out requests handled for you',
      'Hand-off to a human with full context',
    ],
    mockup: <AutomationMockup />,
  },
  {
    id: 'contacts',
    label: 'Contacts & opt-in',
    title: 'Know who agreed to hear from you — and how.',
    body: 'WhatsApp requires consent before you message someone. Every contact carries a record of where and when they opted in, and opt-outs are respected everywhere.',
    points: [
      'CSV import with duplicate and format checks',
      'Tags, lists and custom fields',
      'Opt-in source and timestamp on every contact',
      'Exports for your own compliance records',
    ],
    mockup: <ContactsMockup />,
  },
  {
    id: 'analytics',
    label: 'Analytics',
    title: 'See what was delivered, read and answered.',
    body: 'Meta reports each message’s status in real time. We turn those events into clear campaign reports, including why a message failed.',
    points: [
      'Sent, delivered, read and replied for every campaign',
      'Failure reasons in plain language',
      'Meta charges per campaign and per month',
      'Download reports as CSV',
    ],
    mockup: <AnalyticsMockup />,
  },
  {
    id: 'team',
    label: 'Numbers & roles',
    title: 'Multiple numbers, controlled access.',
    body: 'Run separate numbers for sales and support, and decide exactly who can send campaigns, reply to customers or only view reports.',
    points: [
      'Several WhatsApp numbers in one workspace',
      'Admin, agent and viewer roles',
      'Per-number access for agents',
      'Quality rating for each number, straight from Meta',
    ],
    mockup: <TeamMockup />,
  },
]

export function Features() {
  const tabs: TabItem[] = features.map((feature) => ({
    id: feature.id,
    label: feature.label,
    content: (
      <div className="grid items-start gap-10 lg:grid-cols-12">
        <div className="lg:col-span-5">
          <h3 className="font-display text-[1.7rem] font-semibold leading-[1.1] tracking-[-0.025em] md:text-[2rem]">
            {feature.title}
          </h3>
          <p className="mt-4 text-[16px] leading-relaxed text-muted">{feature.body}</p>
          <ul className="mt-6 space-y-3 border-t border-line pt-6 text-[15px]">
            {feature.points.map((point) => (
              <li key={point} className="flex gap-2.5">
                <Check className="mt-0.5 size-4 shrink-0 text-accent-2" aria-hidden="true" />
                {point}
              </li>
            ))}
          </ul>
        </div>
        <ScrollDepth className="min-w-0 lg:col-span-7">{feature.mockup}</ScrollDepth>
      </div>
    ),
  }))

  return (
    <section id="product" className="py-16 md:py-28">
      <Container>
        <SectionHeader
          index="04"
          eyebrow="Product"
          title="Everything you need to run WhatsApp as a real channel."
          description="Campaigns, reminders, conversations and reporting in one workspace — built around how WhatsApp’s official platform actually works."
        />
        <div className="mt-12 max-md:mt-8">
          <Tabs items={tabs} label="Product features" autoAdvanceMs={7000} />
        </div>
      </Container>
    </section>
  )
}
