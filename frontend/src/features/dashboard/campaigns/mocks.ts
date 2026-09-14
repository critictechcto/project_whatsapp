import type { Schemas } from '../../../api/types'
import { mockRealtime } from '../../../mocks/realtime'
import {
  authorize,
  errorResponse,
  http,
  mockDelay,
  notFound,
  nowIso,
  paginate,
  validationError,
  type MockErrorResponse,
} from '../../../mocks/utils'
import type { AreaMockHandlers } from '../registry/types'
import {
  advanceCampaigns,
  campaignRecords,
  evaluateAudience,
  findCampaign,
  materialise,
  mockTemplate,
  phoneSummary,
  refreshCampaign,
  templateRef,
  toCampaign,
  toRecipient,
  type CampaignRecord,
} from './mockState'

type Campaign = Schemas['Campaign']
type CampaignStatus = Schemas['CampaignStatusEnum']
type WriteBody = Partial<Schemas['CampaignWriteRequest']>

function emitProgress(record: CampaignRecord) {
  const { id, status, stats } = record.campaign
  mockRealtime.emit('campaign.progress', { campaign_id: id, status, stats }, record.workspaceId)
}

function isPast(iso: string) {
  return new Date(iso).getTime() <= Date.now()
}

/** Field errors like the backend serializer's. */
function validateWrite(workspaceId: string, body: WriteBody, partial: boolean): Record<string, string[]> {
  const errors: Record<string, string[]> = {}
  if (!partial || body.name !== undefined) {
    if (!body.name?.trim()) errors.name = ['This field may not be blank.']
    else if (body.name.length > 120) errors.name = ['Ensure this field has no more than 120 characters.']
  }
  if ((!partial || body.template_id !== undefined) && !mockTemplate(workspaceId, body.template_id)) {
    errors.template_id = ['Choose a template from this workspace.']
  }
  if (body.scheduled_at && isPast(body.scheduled_at)) errors.scheduled_at = ['Choose a time in the future.']
  return errors
}

function applyWrite(record: CampaignRecord, body: WriteBody) {
  const campaign = record.campaign
  if (body.name !== undefined) campaign.name = body.name.trim()
  const template = mockTemplate(record.workspaceId, body.template_id)
  if (template) campaign.template = templateRef(template)
  if (body.audience) {
    campaign.audience = { tag_ids: body.audience.tag_ids ?? [], match: body.audience.match ?? 'any', contact_ids: body.audience.contact_ids ?? [] }
  }
  if (body.variable_mapping) {
    campaign.variable_mapping = {
      header: body.variable_mapping.header ?? null,
      body: body.variable_mapping.body ?? [],
      buttons: body.variable_mapping.buttons ?? {},
    }
  }
  if (body.scheduled_at !== undefined && campaign.status === 'draft') campaign.scheduled_at = body.scheduled_at
  if (body.scheduled_at && campaign.status === 'scheduled') campaign.scheduled_at = body.scheduled_at
  campaign.updated_at = nowIso()
  refreshCampaign(record)
}

type Action = 'pause' | 'resume' | 'cancel'

const transitions: Record<Action, { from: readonly CampaignStatus[]; to: CampaignStatus; verb: string }> = {
  pause: { from: ['running'], to: 'paused', verb: 'paused' },
  resume: { from: ['paused'], to: 'running', verb: 'resumed' },
  cancel: { from: ['scheduled', 'running', 'paused'], to: 'cancelled', verb: 'cancelled' },
}

function applyTransition(request: Request, id: string, action: Action): { campaign: Campaign } | { error: MockErrorResponse } {
  const ctx = authorize(request, 'admin')
  if (ctx instanceof Response) return { error: ctx }
  const record = findCampaign(ctx.workspace.id, id)
  if (!record) return { error: notFound() }
  const rule = transitions[action]
  const campaign = record.campaign
  if (!rule.from.includes(campaign.status)) {
    return {
      error: errorResponse(409, 'invalid_campaign_transition', `A ${campaign.status} campaign can't be ${rule.verb}.`, {
        status: campaign.status,
      }),
    }
  }
  campaign.status = rule.to
  campaign.updated_at = nowIso()
  if (action === 'resume') campaign.last_error = ''
  if (action === 'cancel') campaign.completed_at = nowIso()
  refreshCampaign(record)
  emitProgress(record)
  return { campaign: toCampaign(record) }
}

export const handlers: AreaMockHandlers = [
  http.get('/api/v1/campaigns/', ({ request, query, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const status = query.get('status')
    const items = campaignRecords()
      .filter((record) => record.workspaceId === ctx.workspace.id && (!status || record.campaign.status === status))
      .sort((a, b) => b.campaign.created_at.localeCompare(a.campaign.created_at))
      .map(toCampaign)
    return response(200).json(paginate(request, items))
  }),

  http.post('/api/v1/campaigns/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const body = (await request.json()) as WriteBody
    const errors = validateWrite(ctx.workspace.id, body, false)
    if (Object.keys(errors).length) return response.untyped(validationError(errors))

    const template = mockTemplate(ctx.workspace.id, body.template_id)!
    const now = nowIso()
    const record: CampaignRecord = {
      workspaceId: ctx.workspace.id,
      campaign: {
        id: crypto.randomUUID(),
        name: '',
        status: 'draft',
        template: templateRef(template),
        phone_number: phoneSummary(),
        audience: { tag_ids: [], match: 'any', contact_ids: [] },
        variable_mapping: { header: null, body: [], buttons: {} },
        scheduled_at: null,
        started_at: null,
        completed_at: null,
        consent_attested: false,
        stats: { total: 0, skipped: 0, queued: 0, sent: 0, delivered: 0, read: 0, failed: 0, replied: 0 },
        estimated_cost: null,
        last_error: '',
        created_by: { id: ctx.user.id, full_name: ctx.user.full_name ?? "", email: ctx.user.email ?? "" },
        created_at: now,
        updated_at: now,
      },
      recipients: [],
    }
    applyWrite(record, body)
    campaignRecords().push(record)
    return response(201).json(toCampaign(record))
  }),

  http.get('/api/v1/campaigns/{id}/', ({ request, params, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const record = findCampaign(ctx.workspace.id, params.id)
    return record ? response(200).json(toCampaign(record)) : response.untyped(notFound())
  }),

  http.patch('/api/v1/campaigns/{id}/', async ({ request, params, response }) => {
    await mockDelay(150)
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const record = findCampaign(ctx.workspace.id, params.id)
    if (!record) return response.untyped(notFound())
    if (record.campaign.status !== 'draft' && record.campaign.status !== 'scheduled') {
      return response.untyped(
        errorResponse(409, 'campaign_not_editable', 'Only draft and scheduled campaigns can be changed.', { status: record.campaign.status }),
      )
    }
    const body = (await request.json()) as WriteBody
    const errors = validateWrite(ctx.workspace.id, body, true)
    if (Object.keys(errors).length) return response.untyped(validationError(errors))
    applyWrite(record, body)
    return response(200).json(toCampaign(record))
  }),

  http.delete('/api/v1/campaigns/{id}/', ({ request, params, response }) => {
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const record = findCampaign(ctx.workspace.id, params.id)
    if (!record) return response.untyped(notFound())
    if (record.campaign.status !== 'draft') {
      return response.untyped(errorResponse(409, 'campaign_not_editable', 'Only draft campaigns can be deleted.'))
    }
    const records = campaignRecords()
    records.splice(records.indexOf(record), 1)
    return response(204).empty()
  }),

  http.post('/api/v1/campaigns/{id}/audience-preview/', async ({ request, params, response }) => {
    await mockDelay(150)
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const record = findCampaign(ctx.workspace.id, params.id)
    if (!record) return response.untyped(notFound())
    const { preview } = evaluateAudience(ctx.workspace.id, record.campaign.audience, record.campaign.template.category)
    return response(200).json(preview)
  }),

  http.post('/api/v1/campaigns/{id}/launch/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const record = findCampaign(ctx.workspace.id, params.id)
    if (!record) return response.untyped(notFound())
    const campaign = record.campaign
    if (campaign.status !== 'draft' && campaign.status !== 'scheduled') {
      return response.untyped(
        errorResponse(409, 'invalid_campaign_transition', `A ${campaign.status} campaign can't be launched.`, { status: campaign.status }),
      )
    }
    const body = (await request.json()) as Partial<Schemas['LaunchCampaignRequest']>
    if (body.consent_attested !== true) {
      return response.untyped(validationError({ consent_attested: ['Confirm that every recipient agreed to receive these messages.'] }))
    }
    if (body.scheduled_at && isPast(body.scheduled_at)) {
      return response.untyped(validationError({ scheduled_at: ['Choose a time in the future.'] }))
    }
    const template = mockTemplate(ctx.workspace.id, campaign.template.id)
    if (template?.status !== 'APPROVED') {
      return response.untyped(errorResponse(409, 'template_not_approved', 'The template is not approved by Meta.'))
    }
    const { preview } = evaluateAudience(ctx.workspace.id, campaign.audience, campaign.template.category)
    if (preview.eligible === 0) {
      return response.untyped(
        validationError({ audience: ['Nobody in this audience can receive the campaign: they are opted out or have no marketing opt-in.'] }),
      )
    }

    const now = nowIso()
    campaign.consent_attested = true
    campaign.updated_at = now
    if (body.scheduled_at) {
      campaign.status = 'scheduled'
      campaign.scheduled_at = body.scheduled_at
    } else {
      campaign.status = 'running'
      campaign.scheduled_at = null
      campaign.started_at = now
      materialise(record, now)
    }
    refreshCampaign(record)
    emitProgress(record)
    return response(200).json(toCampaign(record))
  }),

  http.post('/api/v1/campaigns/{id}/pause/', async ({ request, params, response }) => {
    await mockDelay()
    const result = applyTransition(request, params.id, 'pause')
    return 'error' in result ? response.untyped(result.error) : response(200).json(result.campaign)
  }),

  http.post('/api/v1/campaigns/{id}/resume/', async ({ request, params, response }) => {
    await mockDelay()
    const result = applyTransition(request, params.id, 'resume')
    return 'error' in result ? response.untyped(result.error) : response(200).json(result.campaign)
  }),

  http.post('/api/v1/campaigns/{id}/cancel/', async ({ request, params, response }) => {
    await mockDelay()
    const result = applyTransition(request, params.id, 'cancel')
    return 'error' in result ? response.untyped(result.error) : response(200).json(result.campaign)
  }),

  http.get('/api/v1/campaigns/{id}/recipients/', ({ request, params, query, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const record = findCampaign(ctx.workspace.id, params.id)
    if (!record) return response.untyped(notFound())
    const status = query.get('status')
    const items = record.recipients.filter((recipient) => !status || recipient.status === status).map(toRecipient)
    return response(200).json(paginate(request, items))
  }),
]

// Mock sender for the browser demo: progresses running campaigns and pushes `campaign.progress`.
// Tests drive progress explicitly instead.
const TICKER_KEY = '__upchatzCampaignTicker'
if (import.meta.env.MODE !== 'test' && typeof window !== 'undefined') {
  const scope = window as unknown as Record<string, number | undefined>
  if (scope[TICKER_KEY] !== undefined) window.clearInterval(scope[TICKER_KEY])
  scope[TICKER_KEY] = window.setInterval(() => {
    for (const record of advanceCampaigns()) emitProgress(record)
  }, 4000)
}
