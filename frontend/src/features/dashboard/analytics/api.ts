/**
 * Every analytics API call lives here. `backend/openapi.yml` has no analytics paths yet, so the reports
 * go through the untyped `apiFetch` (same auth, refresh and `X-Workspace-ID` handling as `api`) with
 * the hand-written types in `./types`. Once the schema is regenerated, swap `apiFetch<T>(path)` for
 * `unwrap(api.GET('/api/v1/analytics/<report>/', { params: { query: range }, signal }))` and the types
 * for `Schemas[...]`; nothing outside this file needs to change.
 */
import { useQuery } from '@tanstack/react-query'
import { apiFetch, authFetch } from '../../../api/client'
import { ApiError, isApiError } from '../../../api/errors'
import { workspaceKeys } from '../../../api/queryKeys'
import { env } from '../../../config/env'
import { useWorkspace } from '../../../lib/workspace'
import type {
  AnalyticsCampaigns,
  AnalyticsCommerce,
  AnalyticsMessages,
  AnalyticsOverview,
  AnalyticsReport,
  AnalyticsTeam,
  AnalyticsTemplates,
  DateRange,
} from './types'

export const analyticsKeys = workspaceKeys('analytics')

export const ANALYTICS_BASE = '/api/v1/analytics/'

function rangeQuery(range: DateRange, extra: Record<string, string> = {}): string {
  return new URLSearchParams({ ...extra, from: range.from, to: range.to }).toString()
}

type ReportResponses = {
  overview: AnalyticsOverview
  messages: AnalyticsMessages
  templates: AnalyticsTemplates
  campaigns: AnalyticsCampaigns
  team: AnalyticsTeam
  commerce: AnalyticsCommerce
}

export function fetchReport<K extends keyof ReportResponses>(report: K, range: DateRange, signal?: AbortSignal) {
  return apiFetch<ReportResponses[K]>(`${ANALYTICS_BASE}${report}/?${rangeQuery(range)}`, { signal })
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
  // An older backend may omit details; the analytics endpoints only gate on these two features.
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
  const response = await authFetch(new Request(`${env.apiUrl}${ANALYTICS_BASE}export/?${rangeQuery(range, { report })}`))
  if (!response.ok) throw await ApiError.fromResponse(response)
  const filename = filenameFromDisposition(response.headers.get('Content-Disposition')) ?? `upchatz-${report}-${range.from}-${range.to}.csv`
  const blob = await response.blob()
  if (typeof URL.createObjectURL === 'function') {
    const url = URL.createObjectURL(blob)
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
