import { HttpResponse } from 'msw'
import type { Schemas } from '../../../api/types'
import { db, type Mutable } from '../../../mocks/db'
import { daysAgo, ids, seedTemplates } from '../../../mocks/seed'
import { authorize, errorResponse, http, mockDelay, notFound, nowIso, paginate, uuid, validationError } from '../../../mocks/utils'
import type { AreaMockHandlers } from '../registry/types'
import { validateTemplate } from './lib/validate'

type MockTemplate = Mutable<Schemas['MessageTemplate']> & {
  /** When a PENDING template flips to APPROVED (ms epoch), checked on the next fetch. */
  reviewAt?: number
}

/** Tunable from tests. Review is slow enough in tests that a submitted template stays pending. */
export const templateMockConfig = {
  reviewDelayMs: import.meta.env.MODE === 'test' ? 60_000 : 8_000,
}

type Seed = Pick<MessageTemplate, 'id' | 'name' | 'language' | 'category' | 'status' | 'components'> & {
  quality?: Schemas['TemplateQualityScoreEnum']
  rejected_reason?: string
  age: number
}
type MessageTemplate = Schemas['MessageTemplate']

const templateId = (suffix: string) => `a4e1c3b5-7d9f-4b2a-8c6e-0f1a2b3c4d${suffix}`

/** Extra demo templates on top of the shared seeds (which keep their ids for other areas). */
const extraSeeds: Seed[] = [
  {
    id: templateId('55'),
    name: 'order_shipped',
    language: 'hi',
    category: 'UTILITY',
    status: 'APPROVED',
    quality: 'GREEN',
    age: 20,
    components: [
      { type: 'HEADER', format: 'TEXT', text: 'ऑर्डर {{1}} भेज दिया गया है', example: { header_text: ['SS-10482'] } },
      {
        type: 'BODY',
        text: 'नमस्ते {{1}}, आपका ऑर्डर *{{2}}* भेज दिया गया है और {{3}} तक पहुँच जाएगा।',
        example: { body_text: [['अनन्या', '1 किलो काजू कतली', '14 सितंबर']] },
      },
      { type: 'FOOTER', text: 'शर्मा स्वीट्स, जयपुर' },
      {
        type: 'BUTTONS',
        buttons: [
          { type: 'URL', text: 'ऑर्डर ट्रैक करें', url: 'https://sharmasweets.in/track/{{1}}', example: ['https://sharmasweets.in/track/SS-10482'] },
        ],
      },
    ],
  },
  {
    id: templateId('56'),
    name: 'diwali_offer_2026',
    language: 'en',
    category: 'MARKETING',
    status: 'APPROVED',
    quality: 'YELLOW',
    age: 12,
    components: [
      { type: 'HEADER', format: 'IMAGE', example: { header_handle: ['4::aW1hZ2UvanBlZw==:ARbDiwaliHamper2026'] } },
      {
        type: 'BODY',
        text: 'Happy Diwali, {{1}}! Get *{{2}} off* on sweet boxes and dry-fruit hampers till {{3}}. Use the code below at checkout.',
        example: { body_text: [['Kabir', '20%', '2 Nov']] },
      },
      { type: 'FOOTER', text: 'Reply STOP to opt out' },
      {
        type: 'BUTTONS',
        buttons: [
          { type: 'COPY_CODE', example: 'DIWALI26' },
          { type: 'URL', text: 'Shop hampers', url: 'https://sharmasweets.in/diwali' },
          { type: 'QUICK_REPLY', text: 'Stop promotions' },
        ],
      },
    ],
  },
  {
    id: templateId('57'),
    name: 'otp_login',
    language: 'en',
    category: 'AUTHENTICATION',
    status: 'APPROVED',
    quality: 'GREEN',
    age: 18,
    components: [
      { type: 'BODY', add_security_recommendation: true },
      { type: 'FOOTER', code_expiration_minutes: 10 },
      { type: 'BUTTONS', buttons: [{ type: 'OTP', otp_type: 'COPY_CODE', text: 'Copy code' }] },
    ],
  },
  {
    id: templateId('58'),
    name: 'cod_confirmation',
    language: 'en',
    category: 'UTILITY',
    status: 'PAUSED',
    quality: 'RED',
    age: 50,
    components: [
      {
        type: 'BODY',
        text: 'Hi {{1}}, please confirm your cash-on-delivery order {{2}} of ₹{{3}} before we pack it.',
        example: { body_text: [['Meera', 'SS-10377', '1,480']] },
      },
      { type: 'BUTTONS', buttons: [{ type: 'QUICK_REPLY', text: 'Yes, confirm' }, { type: 'QUICK_REPLY', text: 'Cancel order' }] },
    ],
  },
  {
    id: templateId('59'),
    name: 'wholesale_price_list',
    language: 'en',
    category: 'MARKETING',
    status: 'DISABLED',
    quality: 'RED',
    age: 70,
    components: [
      { type: 'HEADER', format: 'DOCUMENT', example: { header_handle: ['4::YXBwbGljYXRpb24vcGRm:ARbPriceList'] } },
      {
        type: 'BODY',
        text: 'Namaste {{1}}, our wholesale price list for {{2}} is attached. Call us to place a bulk order.',
        example: { body_text: [['Suresh', 'September']] },
      },
      { type: 'BUTTONS', buttons: [{ type: 'PHONE_NUMBER', text: 'Call Sharma Sweets', phone_number: '+919829011223' }] },
    ],
  },
  {
    id: templateId('5a'),
    name: 'delivery_slot_offer',
    language: 'en',
    category: 'UTILITY',
    status: 'REJECTED',
    rejected_reason: 'INCORRECT_CATEGORY',
    age: 6,
    components: [
      {
        type: 'BODY',
        text: 'Hi {{1}}, your delivery slot is {{2}}. Add a box of motichoor laddoos for just ₹199 today!',
        example: { body_text: [['Tara', '12 Sep, 4-6 PM']] },
      },
    ],
  },
  {
    id: templateId('5b'),
    name: 'rakhi_hamper_launch',
    language: 'en',
    category: 'MARKETING',
    status: 'DRAFT',
    age: 2,
    components: [
      { type: 'HEADER', format: 'TEXT', text: 'Raksha Bandhan hampers are here' },
      {
        type: 'BODY',
        text: 'Hi {{1}}, surprise your sibling with our Rakhi hampers starting at ₹{{2}}. Free delivery in Jaipur.',
        example: { body_text: [['Diya', '499']] },
      },
      { type: 'FOOTER', text: 'Reply STOP to opt out' },
    ],
  },
]

function sharedSeeds(): Seed[] {
  return seedTemplates.map((template, index) => ({
    ...(JSON.parse(JSON.stringify(template)) as Omit<Seed, 'age'>),
    quality: template.status === 'APPROVED' ? 'GREEN' : 'UNKNOWN',
    age: 35 - index,
  }))
}

function build(seed: Seed, index: number): MockTemplate {
  const submitted = seed.status !== 'DRAFT'
  return {
    id: seed.id,
    waba: ids.waba,
    meta_template_id: submitted ? `8812${index}4455667788` : '',
    name: seed.name,
    language: seed.language,
    category: seed.category,
    previous_category: seed.id === templateId('5a') ? 'MARKETING' : seed.category,
    status: seed.status,
    rejected_reason: seed.rejected_reason ?? '',
    quality_score: seed.quality ?? 'UNKNOWN',
    components: JSON.parse(JSON.stringify(seed.components)) as MessageTemplate['components'],
    submitted_at: submitted ? daysAgo(seed.age - 0.2) : null,
    last_synced_at: submitted ? daysAgo(1) : null,
    created_by: ids.demoUser,
    created_at: daysAgo(seed.age),
    updated_at: daysAgo(Math.min(seed.age, 1)),
  }
}

type TemplateState = Map<string, MockTemplate[]>

/** `resetMockDb` replaces `db.workspaces` with a new array, so keying on it resets this state too. */
const states = new WeakMap<object, TemplateState>()

function state(): TemplateState {
  let current = states.get(db.workspaces)
  if (!current) {
    current = new Map([[ids.sharmaSweets, [...sharedSeeds(), ...extraSeeds].map(build)]])
    states.set(db.workspaces, current)
  }
  return current
}

function templatesOf(workspaceId: string): MockTemplate[] {
  const all = state()
  if (!all.has(workspaceId)) all.set(workspaceId, [])
  return all.get(workspaceId)!
}

/** Seeded WABAs: only Sharma Sweets is connected (matches the shared WhatsApp fallbacks). */
function wabaIds(workspaceId: string): string[] {
  return workspaceId === ids.sharmaSweets ? [ids.waba] : []
}

function resolveReviews(templates: MockTemplate[]) {
  const now = Date.now()
  for (const template of templates) {
    if (template.status === 'PENDING' && template.reviewAt !== undefined && template.reviewAt <= now) {
      template.status = 'APPROVED'
      template.quality_score = 'UNKNOWN'
      template.last_synced_at = nowIso()
      template.updated_at = nowIso()
      delete template.reviewAt
    }
  }
}

function serialize(template: MockTemplate): MessageTemplate {
  const { reviewAt: _reviewAt, ...rest } = template
  return rest
}

const editable = (template: MockTemplate) => template.status === 'DRAFT' || template.status === 'REJECTED'

const duplicateNameError = () =>
  validationError({ name: ['A template with this name and language already exists for this account.'] })

type WriteBody = Partial<Record<'waba' | 'name' | 'language' | 'category' | 'components', unknown>>

export const handlers: AreaMockHandlers = [
  http.get('/api/v1/templates/', ({ request, query, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const templates = templatesOf(ctx.workspace.id)
    resolveReviews(templates)
    const status = query.get('status')
    const category = query.get('category')
    const language = query.get('language')
    const waba = query.get('waba')
    const search = (query.get('search') ?? '').toLowerCase()
    const items = templates
      .filter(
        (t) =>
          (!status || t.status === status) &&
          (!category || t.category === category) &&
          (!language || t.language === language) &&
          (!waba || t.waba === waba) &&
          (!search || t.name.includes(search)),
      )
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .map(serialize)
    return response(200).json(paginate(request, items))
  }),

  http.post('/api/v1/templates/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const body = (await request.json()) as WriteBody
    if (typeof body.waba !== 'string' || !wabaIds(ctx.workspace.id).includes(body.waba)) {
      return response.untyped(validationError({ waba: [`Invalid pk "${String(body.waba ?? '')}" - object does not exist.`] }))
    }
    const errors = validateTemplate(body as Required<WriteBody>)
    if (Object.keys(errors).length) return response.untyped(validationError(errors))
    const templates = templatesOf(ctx.workspace.id)
    if (templates.some((t) => t.waba === body.waba && t.name === body.name && t.language === body.language)) {
      return response.untyped(duplicateNameError())
    }
    const now = nowIso()
    const template: MockTemplate = {
      id: uuid(),
      waba: body.waba,
      meta_template_id: '',
      name: body.name as string,
      language: body.language as string,
      category: body.category as MessageTemplate['category'],
      previous_category: body.category as MessageTemplate['category'],
      status: 'DRAFT',
      rejected_reason: '',
      quality_score: 'UNKNOWN',
      components: body.components as MessageTemplate['components'],
      submitted_at: null,
      last_synced_at: null,
      created_by: ctx.user.id,
      created_at: now,
      updated_at: now,
    }
    templates.push(template)
    return response(201).json(serialize(template))
  }),

  http.get('/api/v1/templates/{id}/', ({ request, params, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const templates = templatesOf(ctx.workspace.id)
    resolveReviews(templates)
    const template = templates.find((t) => t.id === params.id)
    return template ? response(200).json(serialize(template)) : response.untyped(notFound())
  }),

  http.patch('/api/v1/templates/{id}/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const templates = templatesOf(ctx.workspace.id)
    const template = templates.find((t) => t.id === params.id)
    if (!template) return response.untyped(notFound())
    if (!editable(template)) {
      return response.untyped(errorResponse(409, 'template_not_editable', 'Only draft or rejected templates can be changed.'))
    }
    const body = (await request.json()) as WriteBody
    if (template.meta_template_id) {
      const locked = (['waba', 'name', 'language'] as const).filter((field) => field in body && body[field] !== template[field])
      if (locked.length) {
        return response.untyped(validationError(Object.fromEntries(locked.map((field) => [field, ['Cannot be changed after the template was submitted.']]))))
      }
    }
    const next = { ...template, ...body } as MockTemplate
    const errors = validateTemplate(next)
    if (Object.keys(errors).length) return response.untyped(validationError(errors))
    if (templates.some((t) => t.id !== template.id && t.waba === next.waba && t.name === next.name && t.language === next.language)) {
      return response.untyped(duplicateNameError())
    }
    Object.assign(template, next, { updated_at: nowIso() })
    return response(200).json(serialize(template))
  }),

  http.delete('/api/v1/templates/{id}/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const templates = templatesOf(ctx.workspace.id)
    const index = templates.findIndex((t) => t.id === params.id)
    if (index === -1) return response.untyped(notFound())
    templates.splice(index, 1)
    return response.untyped(new HttpResponse(null, { status: 204 }))
  }),

  http.post('/api/v1/templates/{id}/submit/', async ({ request, params, response }) => {
    await mockDelay(500)
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const template = templatesOf(ctx.workspace.id).find((t) => t.id === params.id)
    if (!template) return response.untyped(notFound())
    if (!editable(template)) {
      return response.untyped(errorResponse(409, 'template_not_submittable', 'Only draft or rejected templates can be submitted.'))
    }
    const errors = validateTemplate(template)
    if (Object.keys(errors).length) return response.untyped(validationError(errors))
    const now = nowIso()
    Object.assign(template, {
      meta_template_id: template.meta_template_id || String(Date.now()),
      status: 'PENDING',
      rejected_reason: '',
      submitted_at: now,
      updated_at: now,
      reviewAt: Date.now() + templateMockConfig.reviewDelayMs,
    })
    return response(200).json(serialize(template))
  }),

  http.post('/api/v1/templates/sync/', async ({ request, response }) => {
    await mockDelay(600)
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const templates = templatesOf(ctx.workspace.id)
    resolveReviews(templates)
    const now = nowIso()
    for (const template of templates) if (template.meta_template_id) template.last_synced_at = now
    return response(202).json({ queued: wabaIds(ctx.workspace.id) })
  }),
]
