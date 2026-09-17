import { HttpResponse } from 'msw'
import { authorize, errorResponse, http, mockDelay, validationError } from '../../../mocks/utils'
import type { AreaMockHandlers } from '../registry/types'
import {
  campaignsReport,
  commerceReport,
  exportCsv,
  messages,
  mockPlanFeatures,
  overview,
  teamReport,
  templatesReport,
} from './mockData'
import { MAX_RANGE_DAYS, daysInRange, isValidDate, presetRange, todayIn, type DateRange } from './range'

/**
 * Analytics handlers (typed against `openapi.yml`). Every report reads the same seeded days
 * (`mockData.ts`), validates `from`/`to` like the API and applies the plan gates: Sharma Sweets has
 * analytics and commerce, Kaveri (Starter) has neither.
 */

type Gate = 'analytics' | 'commerce'

type Resolved = { error: Response } | { workspaceId: string; range: DateRange; today: string; timeZone: string }

function featureUnavailable(feature: Gate) {
  const message =
    feature === 'analytics' ? 'Analytics is not included in your plan.' : 'Selling on WhatsApp is not included in your plan.'
  return errorResponse(409, 'feature_not_available', message, { feature })
}

function resolve(request: Request, gates: Gate[]): Resolved {
  const ctx = authorize(request)
  if (ctx instanceof Response) return { error: ctx }
  const features = mockPlanFeatures[ctx.workspace.id] ?? { analytics: false, commerce: false }
  for (const gate of gates) if (!features[gate]) return { error: featureUnavailable(gate) }

  const timeZone = ctx.workspace.time_zone || 'Asia/Kolkata'
  const today = todayIn(timeZone)
  const url = new URL(request.url)
  const to = url.searchParams.get('to') || today
  const from = url.searchParams.get('from') || presetRange(30, to).from

  // Same checks and field keys as the API (`apps/analytics/ranges.py`).
  const errors: Record<string, string[]> = {}
  if (!isValidDate(from)) errors.from = ['Date has wrong format. Use one of these formats instead: YYYY-MM-DD.']
  if (!isValidDate(to)) errors.to = ['Date has wrong format. Use one of these formats instead: YYYY-MM-DD.']
  if (!errors.from && !errors.to) {
    if (to > today) errors.to = ["The end date can't be in the future."]
    else if (from > to) errors.from = ['The start date must be on or before the end date.']
    else if (daysInRange(from, to) > MAX_RANGE_DAYS) errors.from = [`The range can be at most ${MAX_RANGE_DAYS} days.`]
  }
  if (Object.keys(errors).length) return { error: validationError(errors) }
  return { workspaceId: ctx.workspace.id, range: { from, to }, today, timeZone }
}

const commerceGates: Gate[] = ['analytics', 'commerce']

export const handlers: AreaMockHandlers = [
  http.get('/api/v1/analytics/overview/', async ({ request, response }) => {
    await mockDelay(300)
    const r = resolve(request, ['analytics'])
    return 'error' in r ? response.untyped(r.error) : response(200).json(overview(r.workspaceId, r.range, r.today, r.timeZone))
  }),
  http.get('/api/v1/analytics/messages/', async ({ request, response }) => {
    await mockDelay(300)
    const r = resolve(request, ['analytics'])
    return 'error' in r ? response.untyped(r.error) : response(200).json(messages(r.workspaceId, r.range, r.today, r.timeZone))
  }),
  http.get('/api/v1/analytics/templates/', async ({ request, response }) => {
    await mockDelay(300)
    const r = resolve(request, ['analytics'])
    return 'error' in r ? response.untyped(r.error) : response(200).json(templatesReport(r.workspaceId, r.range, r.today, r.timeZone))
  }),
  http.get('/api/v1/analytics/campaigns/', async ({ request, response }) => {
    await mockDelay(300)
    const r = resolve(request, ['analytics'])
    return 'error' in r ? response.untyped(r.error) : response(200).json(campaignsReport(r.workspaceId, r.range, r.today, r.timeZone))
  }),
  http.get('/api/v1/analytics/team/', async ({ request, response }) => {
    await mockDelay(300)
    const r = resolve(request, ['analytics'])
    return 'error' in r ? response.untyped(r.error) : response(200).json(teamReport(r.workspaceId, r.range, r.today, r.timeZone))
  }),
  http.get('/api/v1/analytics/commerce/', async ({ request, response }) => {
    await mockDelay(300)
    const r = resolve(request, commerceGates)
    return 'error' in r ? response.untyped(r.error) : response(200).json(commerceReport(r.workspaceId, r.range, r.today, r.timeZone))
  }),

  http.get('/api/v1/analytics/export/', async ({ request, query, response }) => {
    await mockDelay(400)
    const reportName = query.get('report') ?? ''
    const r = resolve(request, reportName === 'commerce' ? commerceGates : ['analytics'])
    if ('error' in r) return response.untyped(r.error)
    const csv = exportCsv(reportName, r.workspaceId, r.range, r.today, r.timeZone)
    if (csv === null) return response.untyped(validationError({ report: [`"${reportName}" is not a valid choice.`] }))
    return response.untyped(
      new HttpResponse(csv, {
        status: 200,
        headers: {
          'Content-Type': 'text/csv; charset=utf-8',
          'Content-Disposition': `attachment; filename="upchatz-${reportName}-${r.range.from}-${r.range.to}.csv"`,
        },
      }),
    )
  }),
]
