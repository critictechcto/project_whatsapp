/**
 * Read-only fallbacks for data the shell and shared components need (TemplatePicker, home checklist).
 * Feature areas override these by registering handlers for the same paths in `<area>/mocks.ts`.
 */
import type { Schemas } from '../../api/types'
import { daysAgo, ids, indianMobile, indianName, seedPhoneNumber, seedTags, seedTemplates, seedWaba } from '../seed'
import { authorize, http, notFound, paginate } from '../utils'

function templatesFor(workspaceId: string): Schemas['MessageTemplate'][] {
  if (workspaceId !== ids.sharmaSweets) return []
  return seedTemplates.map((template, index) => ({
    id: template.id,
    waba: ids.waba,
    meta_template_id: template.status === 'APPROVED' ? `8812${index}4455667788` : '',
    name: template.name,
    language: template.language,
    category: template.category,
    previous_category: template.category,
    status: template.status,
    rejected_reason: 'rejected_reason' in template ? template.rejected_reason : '',
    quality_score: template.status === 'APPROVED' ? 'GREEN' : 'UNKNOWN',
    components: template.components as unknown as Schemas['MessageTemplate']['components'],
    submitted_at: daysAgo(30 - index),
    last_synced_at: daysAgo(1),
    created_by: ids.demoUser,
    created_at: daysAgo(35 - index),
    updated_at: daysAgo(1),
  }))
}

function contactsFor(workspaceId: string): Schemas['Contact'][] {
  if (workspaceId !== ids.sharmaSweets) return []
  return Array.from({ length: 48 }, (_, i) => {
    const status = i % 9 === 4 ? 'opted_out' : i % 3 === 0 ? 'unknown' : 'opted_in'
    const phone = indianMobile(i)
    return {
      id: `e0f1a2b3-c4d5-4e6f-8a9b-${String(i + 1).padStart(12, '0')}`,
      phone_e164: phone,
      wa_id: phone.slice(1),
      name: indianName(i),
      email: i % 4 === 0 ? `${indianName(i).toLowerCase().replace(/\s/g, '.')}@gmail.com` : '',
      attributes: { city: ['Jaipur', 'Delhi', 'Mumbai', 'Pune'][i % 4] },
      tags: i % 2 === 0 ? [seedTags[0].id] : [],
      marketing_opt_in_status: status,
      opted_in_at: status === 'opted_in' ? daysAgo(40 - (i % 30)) : null,
      opted_out_at: status === 'opted_out' ? daysAgo(3) : null,
      opt_in_source: status === 'opted_in' ? 'website_form' : '',
      last_inbound_at: i % 5 === 0 ? daysAgo(i % 3) : null,
      created_at: daysAgo(60 - i),
      updated_at: daysAgo(i % 7),
    }
  })
}

export const sharedHandlers = [
  http.get('/api/v1/templates/', ({ request, query, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const status = query.get('status')
    const category = query.get('category')
    const search = (query.get('search') ?? '').toLowerCase()
    const items = templatesFor(ctx.workspace.id).filter(
      (t) => (!status || t.status === status) && (!category || t.category === category) && (!search || t.name.includes(search)),
    )
    return response(200).json(paginate(request, items))
  }),

  http.get('/api/v1/templates/{id}/', ({ request, params, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const template = templatesFor(ctx.workspace.id).find((t) => t.id === params.id)
    return template ? response(200).json(template) : response.untyped(notFound())
  }),

  http.get('/api/v1/whatsapp/accounts/', ({ request, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const items = ctx.workspace.id === ids.sharmaSweets ? [{ ...seedWaba, phone_numbers: [seedPhoneNumber] }] : []
    return response(200).json(paginate(request, items))
  }),

  http.get('/api/v1/whatsapp/phone-numbers/', ({ request, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const items = ctx.workspace.id === ids.sharmaSweets ? [seedPhoneNumber] : []
    return response(200).json(paginate(request, items))
  }),

  http.get('/api/v1/contacts/', ({ request, query, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const search = (query.get('search') ?? '').toLowerCase()
    const items = contactsFor(ctx.workspace.id).filter(
      (c) => !search || c.name?.toLowerCase().includes(search) || c.phone_e164.includes(search),
    )
    return response(200).json(paginate(request, items))
  }),

  http.get('/api/v1/contacts/tags/', ({ request, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const items = ctx.workspace.id === ids.sharmaSweets ? [...seedTags] : []
    return response(200).json(paginate(request, items))
  }),
]
