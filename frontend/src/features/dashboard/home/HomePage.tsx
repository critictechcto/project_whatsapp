import type { UseQueryResult } from '@tanstack/react-query'
import { PageHeader } from '../../../components/app'
import { useWorkspace } from '../../../lib/workspace'
import { useMe } from '../auth/session'
import { useOnboarding, useUpdateOnboarding } from '../onboarding/api'
import { COMMERCE_STEPS, goalSteps, type ChecklistStepId } from '../onboarding/goalSteps'
import {
  hasSentCampaign,
  isCommerceUnavailable,
  useHasAutomations,
  useHasContacts,
  useHasTeam,
  usePhoneNumbers,
  useRecentCampaigns,
  useStoreChecklist,
  useTemplateSummary,
} from './api'
import { OrdersTodayCard, StoreSetupCard } from './components/CommerceCards'
import { CampaignsCard, ConnectionCard, ConversationsCard, SubscriptionCard, TemplatesCard } from './components/OverviewCards'
import { SetupChecklist, type SetupStep, type StepState } from './components/SetupChecklist'

type QueryState<T> = Pick<UseQueryResult<T>, 'isPending' | 'isError' | 'data'>

function stepState<T>(query: QueryState<T>, done: (data: T) => boolean): StepState {
  if (query.isError) return 'unknown'
  if (query.isPending || query.data === undefined) return 'loading'
  return done(query.data) ? 'done' : 'todo'
}

/** State of one store checklist item; `missing` when the checklist has no such key. */
function storeItemState(query: QueryState<{ items: readonly { key: string; done: boolean }[] }>, key: string): StepState | 'missing' {
  if (query.isError) return 'unknown'
  if (query.isPending || !query.data) return 'loading'
  const item = query.data.items.find((candidate) => candidate.key === key)
  if (!item) return 'missing'
  return item.done ? 'done' : 'todo'
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
  const storeChecklist = useStoreChecklist()
  const onboarding = useOnboarding()
  const updateOnboarding = useUpdateOnboarding()

  const teamState = ((): StepState => {
    const members = stepState(team.members, Boolean)
    if (members === 'done' || !team.canSeeInvitations) return members
    const invitations = stepState(team.invitations, Boolean)
    if (invitations === 'done') return 'done'
    if (members === 'loading' || invitations === 'loading') return 'loading'
    return members === 'unknown' ? 'unknown' : invitations
  })()

  const stepStates: Record<ChecklistStepId, StepState | 'missing'> = {
    whatsapp: stepState(phones, (page) => page.results.length > 0),
    contacts: stepState(contacts, Boolean),
    templates: stepState(templates, (summary) => summary.total > 0),
    campaigns: stepState(campaigns, (page) => hasSentCampaign(page.results)),
    automations: stepState(automations, Boolean),
    team: teamState,
    products: storeItemState(storeChecklist, 'products_added'),
    payments: storeItemState(storeChecklist, 'payments_configured'),
    store: storeItemState(storeChecklist, 'store_enabled'),
  }

  // Store steps drop out when the workspace can't use commerce (or the checklist lacks the key).
  const commerceUnavailable = storeChecklist.isError && isCommerceUnavailable(storeChecklist.error)
  const steps: SetupStep[] = goalSteps(onboarding.data?.goal ?? '').flatMap((step) => {
    const state = stepStates[step.id]
    if (state === 'missing' || (commerceUnavailable && COMMERCE_STEPS.includes(step.id))) return []
    return [{ ...step, state }]
  })

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={workspace.name}
        title={firstName ? `Welcome, ${firstName}` : 'Welcome'}
        description="Your WhatsApp workspace at a glance."
      />

      {!onboarding.data?.checklist_dismissed && (
        <SetupChecklist steps={steps} onHide={() => updateOnboarding.mutate({ checklist_dismissed: true })} />
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <OrdersTodayCard />
        <StoreSetupCard />
        <ConnectionCard />
        <ConversationsCard />
        <TemplatesCard />
        <CampaignsCard />
        <SubscriptionCard />
      </div>
    </div>
  )
}
