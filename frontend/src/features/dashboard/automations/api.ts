import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '../../../api/client'
import { isApiError } from '../../../api/errors'
import { workspaceKeys } from '../../../api/queryKeys'
import type { Schemas } from '../../../api/types'

export type AutomationRule = Schemas['AutomationRule']
export type AutomationTrigger = Schemas['AutomationTriggerEnum']
export type AutomationActionType = Schemas['AutomationActionTypeEnum']
export type AutomationRun = Schemas['AutomationRun']
export type RunStatus = Schemas['AutomationRunStatusEnum']
export type BusinessHours = Schemas['BusinessHours']
export type BusinessHoursSlot = Schemas['BusinessHoursSlotRequest']
export type RuleWrite = Schemas['AutomationRuleRequest']
export type RulePatch = Schemas['PatchedAutomationRuleRequest']

export const automationKeys = workspaceKeys('automations')

export function sortRules(rules: readonly AutomationRule[]): AutomationRule[] {
  return [...rules].sort((a, b) => a.priority - b.priority || a.created_at.localeCompare(b.created_at))
}

export function rulesListKey(workspaceId: string) {
  return automationKeys.list(workspaceId, { page_size: 100 })
}

/** Every rule, in run order. Workspaces have a handful of rules, so one page is enough. */
export function useRules(workspaceId: string) {
  return useQuery({
    queryKey: rulesListKey(workspaceId),
    queryFn: async ({ signal }) =>
      sortRules((await unwrap(api.GET('/api/v1/automations/rules/', { params: { query: { page_size: 100 } }, signal }))).results),
  })
}

export function useRule(workspaceId: string, id: string | undefined) {
  return useQuery({
    queryKey: automationKeys.detail(workspaceId, id ?? ''),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/automations/rules/{id}/', { params: { path: { id: id ?? '' } }, signal })),
    enabled: Boolean(id),
  })
}

export function usePhoneNumbers(workspaceId: string) {
  return useQuery({
    queryKey: automationKeys.custom(workspaceId, 'phone-numbers'),
    queryFn: async ({ signal }) =>
      (await unwrap(api.GET('/api/v1/whatsapp/phone-numbers/', { params: { query: { page_size: 50 } }, signal }))).results,
    staleTime: 60_000,
  })
}

export function useMembers(workspaceId: string) {
  return useQuery({
    queryKey: automationKeys.custom(workspaceId, 'members'),
    queryFn: async ({ signal }) =>
      (await unwrap(api.GET('/api/v1/workspaces/members/', { params: { query: { page_size: 100 } }, signal }))).results,
    staleTime: 60_000,
  })
}

export function nextPriority(rules: readonly AutomationRule[] | undefined): number {
  return rules?.length ? Math.max(...rules.map((rule) => rule.priority)) + 1 : 0
}

/** PATCH body. The generated type marks fields that have defaults as required, so they are always resent. */
export function patchBody(rule: AutomationRule, changes: { is_active?: boolean; priority?: number } = {}): RulePatch {
  return {
    is_active: rule.is_active,
    keyword_match: rule.keyword_match,
    cooldown_minutes: rule.cooldown_minutes,
    priority: rule.priority,
    stop_processing: rule.stop_processing,
    ...changes,
  }
}

export const triggerInfo: Record<AutomationTrigger, { label: string; description: string }> = {
  keyword: { label: 'Keyword', description: 'A customer sends a message matching one of your keywords, like “price”. Matching ignores case.' },
  first_inbound: { label: 'First message', description: 'A customer writes when they have no open conversation with you.' },
  new_contact: { label: 'New contact', description: 'Someone messages your number for the very first time.' },
  outside_business_hours: { label: 'Outside business hours', description: 'A customer writes while you are closed, based on your business hours.' },
}

export const actionLabels: Record<AutomationActionType, string> = {
  send_text: 'Send text',
  send_template: 'Send template',
  add_tags: 'Add tags',
  assign: 'Assign to member',
  close_conversation: 'Close conversation',
  send_shop_menu: 'Send shop menu',
  send_catalog: 'Send catalog',
  send_collection: 'Send collection',
}

export const runStatusInfo: Record<RunStatus, { label: string; tone: 'green' | 'neutral' | 'red' }> = {
  succeeded: { label: 'Succeeded', tone: 'green' },
  skipped: { label: 'Skipped', tone: 'neutral' },
  failed: { label: 'Failed', tone: 'red' },
}

const featureGateCodes = ['feature_not_available', 'feature_not_in_plan', 'plan_upgrade_required', 'feature_unavailable']

/** The plan doesn't include the feature (keyword automations are plan-gated). */
export function isFeatureGateError(error: unknown): boolean {
  if (!isApiError(error)) return false
  if (featureGateCodes.includes(error.code)) return true
  const details = error.details
  return typeof details === 'object' && details !== null && (details as Record<string, unknown>).feature === 'keyword_automations'
}
