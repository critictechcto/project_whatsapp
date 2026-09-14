import { z } from 'zod'
import type { VariableSource } from '../campaigns/api'
import { variableSourceSchema } from '../campaigns/wizardSchema'
import type { AutomationActionType, AutomationRule, RuleWrite } from './api'

export const actionTypes = ['send_text', 'send_template', 'add_tags', 'assign', 'close_conversation', 'send_shop_menu', 'send_catalog', 'send_collection'] as const
/** Action types the editor can configure today; the shop actions get their fields with the store screens. */
export const editableActionTypes = ['send_text', 'send_template', 'add_tags', 'assign', 'close_conversation'] as const
export const MAX_ACTIONS = 5
export const MAX_KEYWORDS = 50

const actionSchema = z
  .object({
    type: z.enum(actionTypes),
    text: z.string(),
    template_id: z.string(),
    body_params: z.array(variableSourceSchema),
    tag_ids: z.array(z.string()),
    user_id: z.string(),
    collection_id: z.string(),
  })
  .superRefine((action, ctx) => {
    const issue = (path: string, message: string) => ctx.addIssue({ code: 'custom', path: [path], message })
    if (action.type === 'send_text') {
      if (!action.text.trim()) issue('text', 'Enter the message to send.')
      else if (action.text.length > 4096) issue('text', 'WhatsApp text messages can be up to 4,096 characters.')
    }
    if (action.type === 'send_template' && !action.template_id) issue('template_id', 'Choose an approved template.')
    if (action.type === 'add_tags' && !action.tag_ids.length) issue('tag_ids', 'Choose at least one tag.')
    if (action.type === 'assign' && !action.user_id) issue('user_id', 'Choose a team member.')
    if (action.type === 'send_collection' && !action.collection_id) issue('collection_id', 'Choose a collection.')
  })

export const ruleSchema = z
  .object({
    name: z.string().trim().min(1, 'Give the rule a name.').max(120, 'Use 120 characters or fewer.'),
    is_active: z.boolean(),
    trigger: z.enum(['keyword', 'first_inbound', 'new_contact', 'outside_business_hours']),
    keywords: z.array(z.string()).max(MAX_KEYWORDS, `Use ${MAX_KEYWORDS} keywords or fewer.`),
    keyword_match: z.enum(['exact', 'contains']),
    /** Empty means every number. */
    phone_number_id: z.string(),
    actions: z.array(actionSchema).min(1, 'Add at least one action.').max(MAX_ACTIONS, `A rule can have at most ${MAX_ACTIONS} actions.`),
    cooldown_minutes: z.number({ error: 'Enter the cooldown in minutes.' }).int('Use whole minutes.').min(0, "Cooldown can't be negative."),
    stop_processing: z.boolean(),
  })
  .superRefine((rule, ctx) => {
    if (rule.trigger === 'keyword' && rule.keywords.length === 0) {
      ctx.addIssue({ code: 'custom', path: ['keywords'], message: 'Add at least one keyword for the keyword trigger.' })
    }
  })

export type RuleFormValues = z.infer<typeof ruleSchema>
export type ActionFormValues = RuleFormValues['actions'][number]

export function emptyAction(type: AutomationActionType = 'send_text'): ActionFormValues {
  return { type, text: '', template_id: '', body_params: [], tag_ids: [], user_id: '', collection_id: '' }
}

const text = (value: unknown) => (typeof value === 'string' ? value : '')
const strings = (value: unknown) => (Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [])
const sourceTypes: readonly string[] = ['contact_field', 'attribute', 'static']

function sources(value: unknown): VariableSource[] {
  if (!Array.isArray(value)) return []
  return value
    .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null && sourceTypes.includes(String(item.source)))
    .map((item) => ({ source: item.source as VariableSource['source'], value: text(item.value), fallback: text(item.fallback) }))
}

export function ruleToForm(rule: AutomationRule | null): RuleFormValues {
  return {
    name: rule?.name ?? '',
    is_active: rule?.is_active ?? true,
    trigger: rule?.trigger ?? 'keyword',
    keywords: [...(rule?.keywords ?? [])],
    keyword_match: rule?.keyword_match ?? 'exact',
    phone_number_id: rule?.phone_number_id ?? '',
    actions: rule
      ? rule.actions.map((action) => ({
          type: action.type,
          text: text(action.config?.text),
          template_id: text(action.config?.template_id),
          body_params: sources(action.config?.body_params),
          tag_ids: strings(action.config?.tag_ids),
          user_id: text(action.config?.user_id),
          collection_id: text(action.config?.collection_id),
        }))
      : [emptyAction()],
    cooldown_minutes: rule?.cooldown_minutes ?? 0,
    stop_processing: rule?.stop_processing ?? false,
  }
}

export function actionConfig(action: ActionFormValues): Record<string, unknown> {
  switch (action.type) {
    case 'send_text':
      return { text: action.text }
    case 'send_template':
      return { template_id: action.template_id, body_params: action.body_params }
    case 'add_tags':
      return { tag_ids: action.tag_ids }
    case 'assign':
      return { user_id: action.user_id }
    case 'close_conversation':
    case 'send_shop_menu':
    case 'send_catalog':
      return {}
    case 'send_collection':
      return { collection_id: action.collection_id }
  }
}

export function formToBody(values: RuleFormValues, priority: number): RuleWrite {
  return {
    name: values.name.trim(),
    is_active: values.is_active,
    trigger: values.trigger,
    keywords: values.trigger === 'keyword' ? values.keywords : [],
    keyword_match: values.keyword_match,
    phone_number_id: values.phone_number_id || null,
    actions: values.actions.map((action) => ({ type: action.type, config: actionConfig(action) })),
    cooldown_minutes: values.cooldown_minutes,
    priority,
    stop_processing: values.stop_processing,
  }
}

/** The form field that holds each action type's required config. */
export const actionConfigKeys: Record<AutomationActionType, string | null> = {
  send_text: 'text',
  send_template: 'template_id',
  add_tags: 'tag_ids',
  assign: 'user_id',
  close_conversation: null,
  send_shop_menu: null,
  send_catalog: null,
  send_collection: 'collection_id',
}

/** Maps API error paths such as `actions.0.config` onto form fields such as `actions.0.text`. */
export function ruleFieldMap(paths: readonly string[], actions: readonly ActionFormValues[]): Record<string, string> {
  const map: Record<string, string> = {}
  for (const path of paths) {
    const match = /^actions\.(\d+)\.config(?:\.(.+))?$/.exec(path)
    if (!match) continue
    const [, index, rest] = match
    const action = actions[Number(index)]
    const key = rest ?? (action ? actionConfigKeys[action.type] : null)
    map[path] = key ? `actions.${index}.${key}` : `actions.${index}.type`
  }
  return map
}
