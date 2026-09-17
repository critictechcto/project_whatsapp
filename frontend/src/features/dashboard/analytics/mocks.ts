import { HttpResponse } from 'msw'
import { apiUrl, authorize, errorResponse, http, mockDelay, validationError } from '../../../mocks/utils'
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
import { MAX_RANGE_DAYS, daysInRange, isValidDate, presetRange, todayIn } from './range'
import type { DateRange } from './types'

/**
 * Analytics handlers (`docs/contracts/analytics.md`). Untyped until `openapi.yml` has the analytics
 * paths. Every report reads the same seeded days (`mockData.ts`), validates `from`/`to` like the API
 * and applies the plan gates: Sharma Sweets has analytics and commerce, Kaveri (Starter) has neither.
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
  const to = url.searchParams.get('to') ?? today
  const from = url.searchParams.get('from') ?? presetRange(30, to).from

  const errors: Record<string, string[]> = {}
  if (!isValidDate(from)) errors.from = ['Date has wrong format. Use one of these formats instead: YYYY-MM-DD.']
  if (!isValidDate(to)) errors.to = ['Date has wrong format. Use one of these formats instead: YYYY-MM-DD.']
  if (!errors.from && !errors.to) {
    if (to > today) errors.to = ["The end date can't be in the future."]
    else if (from > to) errors.from = ['The start date must be on or before the end date.']
    else if (daysInRange(from, to) > MAX_RANGE_DAYS) errors.non_field_errors = [`Choose a range of at most ${MAX_RANGE_DAYS} days.`]
  }
  if (Object.keys(errors).length) return { error: validationError(errors) }
  return { workspaceId: ctx.workspace.id, range: { from, to }, today, timeZone }
}

type Builder = (workspaceId: string, range: DateRange, today: string, timeZone: string) => unknown

function report(path: string, build: Builder, gates: Gate[] = ['analytics']) {
  return http.untyped.get(apiUrl(`/api/v1/analytics/${path}/`), async ({ request }) => {
    await mockDelay(300)
    const resolved = resolve(request, gates)
    if ('error' in resolved) return resolved.error
    return HttpResponse.json(build(resolved.workspaceId, resolved.range, resolved.today, resolved.timeZone) as Record<string, never>)
  })
}

const exportGates: Record<string, Gate[]> = { commerce: ['analytics', 'commerce'] }

export const handlers: AreaMockHandlers = [
  report('overview', overview),
  report('messages', messages),
  report('templates', templatesReport),
  report('campaigns', campaignsReport),
  report('team', teamReport),
  report('commerce', commerceReport, ['analytics', 'commerce']),

  http.untyped.get(apiUrl('/api/v1/analytics/export/'), async ({ request }) => {
    await mockDelay(400)
    const reportName = new URL(request.url).searchParams.get('report') ?? ''
    const resolved = resolve(request, exportGates[reportName] ?? ['analytics'])
    if ('error' in resolved) return resolved.error
    const csv = exportCsv(reportName, resolved.workspaceId, resolved.range, resolved.today, resolved.timeZone)
    if (csv === null) return validationError({ report: [`"${reportName}" is not a valid choice.`] })
    return new HttpResponse(csv, {
      status: 200,
      headers: {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': `attachment; filename="upchatz-${reportName}-${resolved.range.from}-${resolved.range.to}.csv"`,
      },
    })
  }),
]
