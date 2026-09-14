import type { UseQueryResult } from '@tanstack/react-query'
import { PageHeader } from '../../../components/app'
import { useWorkspace } from '../../../lib/workspace'
import { useMe } from '../auth/session'
import { hasSentCampaign, useHasAutomations, useHasContacts, useHasTeam, usePhoneNumbers, useRecentCampaigns, useTemplateSummary } from './api'
import { CampaignsCard, ConnectionCard, ConversationsCard, SubscriptionCard, TemplatesCard } from './components/OverviewCards'
import { SetupChecklist, type SetupStep, type StepState } from './components/SetupChecklist'

function stepState<T>(query: Pick<UseQueryResult<T>, 'isPending' | 'isError' | 'data'>, done: (data: T) => boolean): StepState {
  if (query.isError) return 'unknown'
  if (query.isPending || query.data === undefined) return 'loading'
  return done(query.data) ? 'done' : 'todo'
}

/** Workspace home: getting-started steps and overview cards, all computed from real list endpoints. */
export function HomePage() {
  const { workspace } = useWorkspace()
  const me = useMe()
  const firstName = me.data?.full_name?.split(' ')[0]

  const phones = usePhoneNumbers()
  const contacts = useHasContacts()
  const templates = useTemplateSummary()
  const campaigns = useRecentCampaigns()
  const automations = useHasAutomations()
  const team = useHasTeam()

  const teamState = ((): StepState => {
    const members = stepState(team.members, Boolean)
    if (members === 'done' || !team.canSeeInvitations) return members
    const invitations = stepState(team.invitations, Boolean)
    if (invitations === 'done') return 'done'
    if (members === 'loading' || invitations === 'loading') return 'loading'
    return members === 'unknown' ? 'unknown' : invitations
  })()

  const steps: SetupStep[] = [
    {
      id: 'whatsapp',
      title: 'Connect WhatsApp',
      description: "Link your business number to the official WhatsApp Business Platform with Meta's Embedded Signup.",
      to: 'whatsapp',
      cta: 'Connect number',
      state: stepState(phones, (page) => page.results.length > 0),
    },
    {
      id: 'contacts',
      title: 'Add contacts',
      description: 'Import customers who agreed to hear from you on WhatsApp, with their opt-in recorded.',
      to: 'contacts',
      cta: 'Add contacts',
      state: stepState(contacts, Boolean),
    },
    {
      id: 'templates',
      title: 'Create a template',
      description: 'Messages you start outside the 24-hour customer service window need a template approved by Meta.',
      to: 'templates',
      cta: 'Create template',
      state: stepState(templates, (summary) => summary.total > 0),
    },
    {
      id: 'campaigns',
      title: 'Send your first campaign',
      description: 'Send an approved template to a tagged group of opted-in contacts, now or on a schedule.',
      to: 'campaigns/new',
      cta: 'New campaign',
      state: stepState(campaigns, (page) => hasSentCampaign(page.results)),
    },
    {
      id: 'automations',
      title: 'Set up an automation',
      description: 'Reply automatically to keywords, first messages or messages outside business hours.',
      to: 'automations',
      cta: 'Add automation',
      state: stepState(automations, Boolean),
    },
    {
      id: 'team',
      title: 'Invite your team',
      description: 'Share the inbox with colleagues and choose what each person can do.',
      to: 'team',
      cta: 'Invite teammates',
      state: teamState,
    },
  ]

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={workspace.name}
        title={firstName ? `Welcome, ${firstName}` : 'Welcome'}
        description="Your WhatsApp workspace at a glance."
      />

      <SetupChecklist steps={steps} />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <ConnectionCard />
        <ConversationsCard />
        <TemplatesCard />
        <CampaignsCard />
        <SubscriptionCard />
      </div>
    </div>
  )
}
