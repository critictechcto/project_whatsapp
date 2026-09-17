/**
 * Every analytics API call lives here, on the typed client (`backend/openapi.yml`); response types are
 * `Schemas['Analytics…']`.
 */
import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '../../../api/client'
import { ApiError, isApiError } from '../../../api/errors'
import { workspaceKeys } from '../../../api/queryKeys'
import type { paths } from '../../../api/schema'
import type { Schemas } from '../../../api/types'
import { useWorkspace } from '../../../lib/workspace'
import type { DateRange } from './range'

export const analyticsKeys = workspaceKeys('analytics')

/** `report` values of `GET /api/v1/analytics/export/`. */
export type AnalyticsReport = NonNullable<paths['/api/v1/analytics/export/']['get']['parameters']['query']>['report']

type ReportResponses = {
  overview: Schemas['AnalyticsOverview']
  messages: Schemas['AnalyticsMessages']
  templates: Schemas['AnalyticsTemplates']
  campaigns: Schemas['AnalyticsCampaigns']
  team: Schemas['AnalyticsTeam']
  commerce: Schemas['AnalyticsCommerce']
}

type Fetchers = { [K in keyof ReportResponses]: (query: DateRange, signal?: AbortSignal) => Promise<ReportResponses[K]> }

const reportFetchers: Fetchers = {
  overview: (query, signal) => unwrap(api.GET('/api/v1/analytics/overview/', { params: { query }, signal })),
  messages: (query, signal) => unwrap(api.GET('/api/v1/analytics/messages/', { params: { query }, signal })),
  templates: (query, signal) => unwrap(api.GET('/api/v1/analytics/templates/', { params: { query }, signal })),
  campaigns: (query, signal) => unwrap(api.GET('/api/v1/analytics/campaigns/', { params: { query }, signal })),
  team: (query, signal) => unwrap(api.GET('/api/v1/analytics/team/', { params: { query }, signal })),
  commerce: (query, signal) => unwrap(api.GET('/api/v1/analytics/commerce/', { params: { query }, signal })),
}

export function fetchReport<K extends keyof ReportResponses>(report: K, range: DateRange, signal?: AbortSignal): Promise<ReportResponses[K]> {
  const fetcher = reportFetchers[report] as Fetchers[K]
  return fetcher({ from: range.from, to: range.to }, signal)
}

function useReport<K extends keyof ReportResponses>(report: K, range: DateRange, enabled = true) {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: analyticsKeys.custom(workspaceId, report, { from: range.from, to: range.to }),
    queryFn: ({ signal }) => fetchReport(report, range, signal),
    enabled,
  })
}

export const useOverview = (range: DateRange) => useReport('overview', range)
export const useMessagesReport = (range: DateRange, enabled = true) => useReport('messages', range, enabled)
export const useTemplatesReport = (range: DateRange, enabled = true) => useReport('templates', range, enabled)
export const useCampaignsReport = (range: DateRange, enabled = true) => useReport('campaigns', range, enabled)
export const useTeamReport = (range: DateRange, enabled = true) => useReport('team', range, enabled)
export const useCommerceReport = (range: DateRange, enabled = true) => useReport('commerce', range, enabled)

/** 409 `feature_not_available` for a plan feature (`analytics` or `commerce`). */
export function isFeatureUnavailable(error: unknown, feature: 'analytics' | 'commerce'): boolean {
  if (!isApiError(error, 'feature_not_available')) return false
  const details = error.details as { feature?: unknown } | null
  // Details may be omitted; the analytics endpoints only gate on these two features.
  return !details || details.feature === undefined || details.feature === feature
}

/** `attachment; filename="upchatz-messages-2026-09-01-2026-09-30.csv"` → the file name. */
export function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null
  const star = /filename\*\s*=\s*(?:UTF-8'')?([^;]+)/i.exec(header)
  if (star) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"|"$/g, ''))
    } catch {
      // Fall back to the plain filename.
    }
  }
  const plain = /filename\s*=\s*"?([^";]+)"?/i.exec(header)
  return plain ? plain[1].trim() : null
}

/**
 * Downloads a report as CSV through the authenticated client (the export needs the Bearer token and
 * workspace header, so a plain link would not work) and saves it with the server's file name.
 */
export async function downloadReportCsv(report: AnalyticsReport, range: DateRange): Promise<string> {
  const { data, error, response } = await api.GET('/api/v1/analytics/export/', {
    params: { query: { report, from: range.from, to: range.to } },
    parseAs: 'blob',
  })
  if (!response.ok || !data) throw new ApiError(response.status, error ?? null)
  const filename = filenameFromDisposition(response.headers.get('Content-Disposition')) ?? `upchatz-${report}-${range.from}-${range.to}.csv`
  if (typeof URL.createObjectURL === 'function') {
    const url = URL.createObjectURL(data)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.rel = 'noopener'
    document.body.append(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 0)
  }
  return filename
}
