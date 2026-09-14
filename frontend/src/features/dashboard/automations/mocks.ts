import type { Schemas } from '../../../api/types'
import { ids, seedPhoneNumber } from '../../../mocks/seed'
import { authorize, errorResponse, http, mockDelay, notFound, nowIso, paginate, validationError, type WorkspaceContext } from '../../../mocks/utils'
import type { AreaMockHandlers } from '../registry/types'
import { automationState, hoursFor, workspaceTimeZone, type MockRule } from './mockState'

type RuleBody = Partial<Schemas['AutomationRuleRequest']>

const TRIGGERS: readonly string[] = ['keyword', 'first_inbound', 'new_contact', 'outside_business_hours']
const TIME = /^([01]\d|2[0-3]):[0-5]\d$/

/** Required config keys per action type, as in the backend's `ACTION_CONFIG_KEYS`. */
const CONFIG_KEYS: Record<string, readonly string[]> = {
  send_text: ['text'],
  send_template: ['template_id'],
  add_tags: ['tag_ids'],
  assign: ['user_id'],
  close_conversation: [],
}

function isBlank(value: unknown) {
  return value === undefined || value === null || (typeof value === 'string' && !value.trim()) || (Array.isArray(value) && value.length === 0)
}

function validateRule(ctx: WorkspaceContext, body: RuleBody): Record<string, unknown> {
  const errors: Record<string, unknown> = {}
  const name = body.name?.trim() ?? ''
  if (!name) errors.name = ['This field may not be blank.']
  else if (name.length > 120) errors.name = ['Ensure this field has no more than 120 characters.']

  if (!body.trigger || !TRIGGERS.includes(body.trigger)) errors.trigger = ['Choose a valid trigger.']

  const keywords = (body.keywords ?? []).filter((keyword) => keyword.trim())
  if (body.trigger === 'keyword' && keywords.length === 0) errors.keywords = ['Add at least one keyword for the keyword trigger.']
  else if (keywords.length > 50) errors.keywords = ['Use at most 50 keywords.']

  const actions = body.actions ?? []
  if (actions.length === 0) errors.actions = ['Add at least one action.']
  else if (actions.length > 5) errors.actions = ['A rule can have at most 5 actions.']
  else {
    const actionErrors = actions.map((action) => {
      const keys = CONFIG_KEYS[action.type]
      if (!keys) return { type: ['Unknown action type.'] }
      const missing = keys.filter((key) => isBlank(action.config?.[key]))
      return missing.length ? { config: [`${action.type} needs: ${missing.join(', ')}.`] } : {}
    })
    if (actionErrors.some((error) => Object.keys(error).length > 0)) errors.actions = actionErrors
  }

  if (body.cooldown_minutes !== undefined && (!Number.isInteger(body.cooldown_minutes) || body.cooldown_minutes < 0)) {
    errors.cooldown_minutes = ['Ensure this value is greater than or equal to 0.']
  }
  if (body.phone_number_id && !(ctx.workspace.id === ids.sharmaSweets && body.phone_number_id === seedPhoneNumber.id)) {
    errors.phone_number_id = ['Choose a number connected to this workspace.']
  }
  return errors
}

/** Kaveri Clinic's plan doesn't include keyword automations. */
function featureGate(ctx: WorkspaceContext, trigger: string | undefined) {
  if (ctx.workspace.id !== ids.kaveriClinic || trigger !== 'keyword') return null
  return errorResponse(403, 'feature_not_available', 'Keyword automations are not included in your plan.', { feature: 'keyword_automations' })
}

function applyRule(rule: MockRule, body: RuleBody) {
  if (body.name !== undefined) rule.name = body.name.trim()
  if (body.is_active !== undefined) rule.is_active = body.is_active
  if (body.trigger !== undefined) rule.trigger = body.trigger
  if (body.keywords !== undefined) rule.keywords = body.keywords.map((keyword) => keyword.trim()).filter(Boolean)
  if (body.keyword_match !== undefined) rule.keyword_match = body.keyword_match
  if (body.phone_number_id !== undefined) rule.phone_number_id = body.phone_number_id
  if (body.actions !== undefined) rule.actions = body.actions.map((action) => ({ type: action.type, config: action.config ?? {} }))
  if (body.cooldown_minutes !== undefined) rule.cooldown_minutes = body.cooldown_minutes
  if (body.priority !== undefined) rule.priority = body.priority
  if (body.stop_processing !== undefined) rule.stop_processing = body.stop_processing
  rule.updated_at = nowIso()
}

function findRule(workspaceId: string, id: string) {
  return automationState().rules.find((record) => record.workspaceId === workspaceId && record.rule.id === id)
}

function hoursResponse(workspaceId: string): Schemas['BusinessHours'] {
  const hours = hoursFor(workspaceId)
  return { enabled: hours.enabled, time_zone: workspaceTimeZone(workspaceId), schedule: hours.schedule.map((slot) => ({ ...slot })) }
}

export const handlers: AreaMockHandlers = [
  http.get('/api/v1/automations/rules/', ({ request, query, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const trigger = query.get('trigger')
    const active = query.get('is_active')
    const items = automationState()
      .rules.filter(
        ({ workspaceId, rule }) =>
          workspaceId === ctx.workspace.id && (!trigger || rule.trigger === trigger) && (active === null || String(rule.is_active) === active),
      )
      .map(({ rule }) => ({ ...rule }))
      .sort((a, b) => a.priority - b.priority || a.created_at.localeCompare(b.created_at))
    return response(200).json(paginate(request, items))
  }),

  http.post('/api/v1/automations/rules/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const body = (await request.json()) as RuleBody
    const errors = validateRule(ctx, body)
    if (Object.keys(errors).length) return response.untyped(validationError(errors))
    const gate = featureGate(ctx, body.trigger)
    if (gate) return response.untyped(gate)

    const now = nowIso()
    const rule: MockRule = {
      id: crypto.randomUUID(),
      name: '',
      is_active: true,
      trigger: 'keyword',
      keywords: [],
      keyword_match: 'exact',
      phone_number_id: null,
      actions: [],
      cooldown_minutes: 0,
      priority: 0,
      stop_processing: false,
      run_count: 0,
      last_triggered_at: null,
      created_at: now,
      updated_at: now,
    }
    applyRule(rule, body)
    automationState().rules.push({ workspaceId: ctx.workspace.id, rule })
    return response(201).json({ ...rule })
  }),

  http.get('/api/v1/automations/rules/{id}/', ({ request, params, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const record = findRule(ctx.workspace.id, params.id)
    return record ? response(200).json({ ...record.rule }) : response.untyped(notFound())
  }),

  http.patch('/api/v1/automations/rules/{id}/', async ({ request, params, response }) => {
    await mockDelay(150)
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const record = findRule(ctx.workspace.id, params.id)
    if (!record) return response.untyped(notFound())
    const body = (await request.json()) as RuleBody
    const merged: RuleBody = { ...record.rule, ...body }
    const errors = validateRule(ctx, merged)
    if (Object.keys(errors).length) return response.untyped(validationError(errors))
    const gate = body.trigger !== undefined || body.keywords !== undefined || body.is_active ? featureGate(ctx, merged.trigger) : null
    if (gate) return response.untyped(gate)
    applyRule(record.rule, body)
    return response(200).json({ ...record.rule })
  }),

  http.delete('/api/v1/automations/rules/{id}/', ({ request, params, response }) => {
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const { rules } = automationState()
    const index = rules.findIndex((record) => record.workspaceId === ctx.workspace.id && record.rule.id === params.id)
    if (index < 0) return response.untyped(notFound())
    rules.splice(index, 1)
    return response(204).empty()
  }),

  http.get('/api/v1/automations/business-hours/', ({ request, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    return response(200).json(hoursResponse(ctx.workspace.id))
  }),

  http.patch('/api/v1/automations/business-hours/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const body = (await request.json()) as Partial<Schemas['PatchedBusinessHoursRequest']>
    const hours = hoursFor(ctx.workspace.id)

    if (body.schedule !== undefined) {
      if (body.schedule.length > 50) return response.untyped(validationError({ schedule: ['Use at most 50 time slots.'] }))
      const slotErrors = body.schedule.map((slot) => {
        const error: Record<string, string[]> = {}
        if (!Number.isInteger(slot.day) || slot.day < 0 || slot.day > 6) error.day = ['Day must be 0 (Monday) to 6 (Sunday).']
        if (!TIME.test(slot.start)) error.start = ['Use HH:MM.']
        if (!TIME.test(slot.end)) error.end = ['Use HH:MM.']
        else if (slot.start === slot.end) error.end = ['Start and end must differ.']
        return error
      })
      if (slotErrors.some((error) => Object.keys(error).length > 0)) return response.untyped(validationError({ schedule: slotErrors }))
      hours.schedule = body.schedule.map(({ day, start, end }) => ({ day, start, end }))
    }
    if (body.enabled !== undefined) hours.enabled = body.enabled
    return response(200).json(hoursResponse(ctx.workspace.id))
  }),

  http.get('/api/v1/automations/runs/', ({ request, query, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const rule = query.get('rule')
    const status = query.get('status')
    const items = automationState()
      .runs.filter(({ workspaceId, run }) => workspaceId === ctx.workspace.id && (!rule || run.rule.id === rule) && (!status || run.status === status))
      .map(({ run }) => run)
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
    return response(200).json(paginate(request, items))
  }),
]
