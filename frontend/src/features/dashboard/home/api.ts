import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '../../../api/client'
import { isApiError } from '../../../api/errors'
import { workspaceKeys } from '../../../api/queryKeys'
import type { Schemas } from '../../../api/types'
import { templateKeys } from '../../../components/app/whatsapp/templateKeys'
import { useWorkspace } from '../../../lib/workspace'

/**
 * Home reads only list endpoints the areas already expose. Keys live under each area's namespace
 * so that area's invalidations refresh home too.
 */
const whatsappKeys = workspaceKeys('whatsapp')
const contactKeys = workspaceKeys('contacts')
const inboxKeys = workspaceKeys('inbox')
const campaignKeys = workspaceKeys('campaigns')
const automationKeys = workspaceKeys('automations')
const teamKeys = workspaceKeys('team')
const billingKeys = workspaceKeys('billing')
const orderKeys = workspaceKeys('orders')
const storeKeys = workspaceKeys('store')

/** Key of the home "Orders today" summary; realtime order frames invalidate it. */
export function orderSummaryKey(workspaceId: string) {
  return orderKeys.custom(workspaceId, 'summary')
}

/**
 * Commerce endpoints the workspace can't use: not mounted (404/501), not allowed (403), or the store
 * or plan lacks commerce (409 `commerce_not_enabled` / `feature_not_available`). Home hides those cards.
 */
export function isCommerceUnavailable(error: unknown): boolean {
  return isNotImplemented(error) || (isApiError(error) && [403, 404, 409].includes(error.status))
}

export function useOrderSummary() {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: orderSummaryKey(workspaceId),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/orders/summary/', { signal })),
    retry,
  })
}

/** Viewers may read the checklist too (docs/contracts/wave-3-commerce.md, Store). */
export function useStoreChecklist() {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: storeKeys.custom(workspaceId, 'checklist'),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/store/checklist/', { signal })),
    retry,
  })
}

type ChecklistItem = Schemas['StoreChecklistItem']

const storeStepLabels: Record<string, string> = {
  whatsapp_connected: 'Connect WhatsApp',
  products_added: 'Add products',
  payments_configured: 'Set up payments',
  order_templates_ready: 'Prepare order update templates',
  alert_number_verified: 'Verify your order alert number',
  store_enabled: 'Turn on your store',
}

/** Label of a store checklist key; unknown keys are humanised (`new_step` → "New step"). */
export function storeStepLabel(key: string): string {
  const known = storeStepLabels[key]
  if (known) return known
  const words = key.replace(/_/g, ' ').trim()
  return words ? words[0].toUpperCase() + words.slice(1) : 'Store step'
}

export type StoreProgress = { done: number; total: number; next: ChecklistItem | null; storeEnabled: boolean }

export function storeProgress(items: readonly ChecklistItem[]): StoreProgress {
  return {
    done: items.filter((item) => item.done).length,
    total: items.length,
    next: items.find((item) => !item.done) ?? null,
    storeEnabled: items.some((item) => item.key === 'store_enabled' && item.done),
  }
}

/** Page size for counting from a list; beyond it, show "200+". */
export const COUNT_PAGE_SIZE = 200

/** Endpoints not built yet answer 501 `not_implemented`; retrying won't help. */
export function isNotImplemented(error: unknown): boolean {
  return isApiError(error) && (error.status === 501 || error.code === 'not_implemented')
}

/** Home shows many small cards; retry a transient failure once, never 4xx or 501. */
const retry = (failureCount: number, error: unknown) => {
  if (isNotImplemented(error) || (isApiError(error) && error.status >= 400 && error.status < 500)) return false
  return failureCount < 1
}

export function usePhoneNumbers() {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: whatsappKeys.list(workspaceId, { area: 'home', page_size: 50 }),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/whatsapp/phone-numbers/', { params: { query: { page_size: 50 } }, signal })),
    retry,
  })
}

export function useHasContacts() {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: contactKeys.list(workspaceId, { area: 'home', page_size: 1 }),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/contacts/', { params: { query: { page_size: 1 } }, signal })),
    select: (page) => page.results.length > 0,
    retry,
  })
}

export function useTemplateSummary() {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: templateKeys.list(workspaceId, { area: 'home', page_size: COUNT_PAGE_SIZE }),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/templates/', { params: { query: { page_size: COUNT_PAGE_SIZE } }, signal })),
    select: (page) => summarizeTemplates(page.results, Boolean(page.next)),
    retry,
  })
}

export type TemplateSummary = {
  total: number
  approved: number
  pending: number
  rejected: number
  /** Paused, disabled or otherwise not sendable. */
  attention: number
  draft: number
  /** More templates exist than were counted. */
  truncated: boolean
}

export function summarizeTemplates(templates: readonly Pick<Schemas['MessageTemplate'], 'status'>[], truncated: boolean): TemplateSummary {
  const summary: TemplateSummary = { total: 0, approved: 0, pending: 0, rejected: 0, attention: 0, draft: 0, truncated }
  for (const { status } of templates) {
    if (status === 'DELETED' || status === 'PENDING_DELETION' || status === 'ARCHIVED') continue
    summary.total += 1
    if (status === 'APPROVED') summary.approved += 1
    else if (status === 'PENDING' || status === 'IN_APPEAL') summary.pending += 1
    else if (status === 'REJECTED') summary.rejected += 1
    else if (status === 'DRAFT') summary.draft += 1
    else summary.attention += 1
  }
  return summary
}

export type Count = { value: number; more: boolean }

export function useConversationCounts() {
  const { workspaceId } = useWorkspace()
  const open = useQuery({
    queryKey: inboxKeys.list(workspaceId, { area: 'home', status: 'open', page_size: COUNT_PAGE_SIZE }),
    queryFn: ({ signal }) =>
      unwrap(api.GET('/api/v1/inbox/conversations/', { params: { query: { status: 'open', page_size: COUNT_PAGE_SIZE } }, signal })),
    select: (page): Count => ({ value: page.results.length, more: Boolean(page.next) }),
    retry,
  })
  const unassigned = useQuery({
    queryKey: inboxKeys.list(workspaceId, { area: 'home', status: 'open', assignee: 'none', page_size: COUNT_PAGE_SIZE }),
    queryFn: ({ signal }) =>
      unwrap(
        api.GET('/api/v1/inbox/conversations/', { params: { query: { status: 'open', assignee: 'none', page_size: COUNT_PAGE_SIZE } }, signal }),
      ),
    select: (page): Count => ({ value: page.results.length, more: Boolean(page.next) }),
    retry,
  })
  return { open, unassigned }
}

export const RECENT_CAMPAIGNS = 5

export function useRecentCampaigns() {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: campaignKeys.list(workspaceId, { area: 'home', page_size: 50 }),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/campaigns/', { params: { query: { page_size: 50 } }, signal })),
    retry,
  })
}

/** True once any campaign has started sending. */
export function hasSentCampaign(campaigns: readonly Pick<Schemas['Campaign'], 'status' | 'started_at'>[]): boolean {
  return campaigns.some((campaign) => Boolean(campaign.started_at) || ['running', 'paused', 'completed'].includes(campaign.status))
}

/** Share of recipients the campaign has finished with (sent, delivered, read, failed or skipped). */
export function campaignProgress(stats: Schemas['CampaignStats']): { processed: number; total: number; percent: number } {
  const processed = stats.skipped + stats.sent + stats.delivered + stats.read + stats.failed
  const total = stats.total
  const percent = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0
  return { processed: Math.min(processed, total), total, percent }
}

export function useHasAutomations() {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: automationKeys.list(workspaceId, { area: 'home', page_size: 1 }),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/automations/rules/', { params: { query: { page_size: 1 } }, signal })),
    select: (page) => page.results.length > 0,
    retry,
  })
}

/** Team step: someone else joined, or (for admins, who can list them) an invitation is pending. */
export function useHasTeam() {
  const { workspaceId, can } = useWorkspace()
  const canSeeInvitations = can('admin')
  const members = useQuery({
    queryKey: teamKeys.list(workspaceId, { area: 'home', kind: 'members', page_size: 2 }),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/workspaces/members/', { params: { query: { page_size: 2 } }, signal })),
    select: (page) => page.results.length > 1,
    retry,
  })
  const invitations = useQuery({
    queryKey: teamKeys.list(workspaceId, { area: 'home', kind: 'invitations', page_size: 1 }),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/workspaces/invitations/', { params: { query: { page_size: 1 } }, signal })),
    select: (page) => page.results.some((invitation) => invitation.status === 'pending'),
    enabled: canSeeInvitations,
    retry,
  })
  return { members, invitations, canSeeInvitations }
}

export function useSubscription() {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: billingKeys.custom(workspaceId, 'subscription'),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/billing/subscription/', { signal })),
    retry: false,
  })
}

const DAY_MS = 24 * 60 * 60 * 1000

/** Whole days left in the trial, rounded up; 0 once it has ended. */
export function trialDaysLeft(trialEndsAt: string | null, now = Date.now()): number | null {
  if (!trialEndsAt) return null
  const ends = Date.parse(trialEndsAt)
  if (Number.isNaN(ends)) return null
  return Math.max(0, Math.ceil((ends - now) / DAY_MS))
}

/** Meta's messaging limit tier, e.g. `TIER_1K` → "1K". Returns null when unknown. */
export function tierLabel(tier: string): string | null {
  const match = /^TIER_(\w+)$/i.exec(tier)
  if (!match) return null
  const value = match[1].toUpperCase()
  return value === 'UNLIMITED' ? 'Unlimited' : value
}

export function countLabel(count: Count): string {
  return count.more ? `${count.value}+` : String(count.value)
}
